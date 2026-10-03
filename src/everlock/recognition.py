"""Reconhecimento de identidades: teste simulado e reconhecimento facial real.

Fluxo real: imagem -> motor (um rosto de boa qualidade -> vetor) -> comparação com os vetores
cadastrados -> identidade candidata -> decisão de autorização (consentimento, retenção, ativa,
horário) -> só então o controlador decide se a trava pode ser liberada. O rosto apenas aponta
uma identidade; quem autoriza é `identities.evaluate()`.

Os limites abaixo são PROVISÓRIOS: foram escolhidos com cautela, mas só medições com imagens
autorizadas do grupo (taxa de falsa aceitação e de falsa rejeição) podem validá-los.
"""

import secrets
from dataclasses import dataclass, replace

from everlock.biometrics import cosine
from everlock.domain import Denied, Event
from everlock.faces import FaceError

MIN_SAMPLES, MAX_SAMPLES = 3, 5
DIRECTION_TEXT = {"left": "esquerda", "right": "direita"}


@dataclass(frozen=True)
class FaceSettings:
    # O SFace documenta 0,363 como ponto de equilíbrio; para acesso, o padrão é mais rígido.
    match_threshold: float = 0.45
    ambiguity_margin: float = 0.05  # entre a melhor identidade e a segunda melhor
    failure_limit: int = 5
    failure_window_seconds: float = 60.0
    turned_slack: float = 0.10
    front_max_yaw: float = 0.15
    turn_min_yaw: float = 0.22
    challenge_seconds: float = 45.0
    open_challenges: int = 20
    max_turned_frames: int = 6


@dataclass(frozen=True)
class Challenge:
    direction: str
    expires_at: float
    session_id: str
    processing: bool = False


def validated_vectors(engine, images, threshold):
    """Lê as fotos de um cadastro. Devolve (vetores, None) ou (None, (status, corpo))."""
    readings, problems = [], []
    for image in images[:MAX_SAMPLES]:
        try:
            readings.append(engine.read(image))
        except FaceError as error:
            if error.code == "engine_unavailable":
                raise
            problems.append(error.message)
    if len(readings) < MIN_SAMPLES:
        reason = f" Motivo mais comum: {problems[0]}" if problems else ""
        return None, (422, {"code": "not_enough_samples", "message": (
            f"Só {len(readings)} de {len(images)} fotos serviram; são necessárias pelo menos "
            f"{MIN_SAMPLES}.{reason}")})
    vectors = [reading.embedding for reading in readings]
    for index, vector in enumerate(vectors):
        others = [cosine(vector, other) for position, other in enumerate(vectors)
                  if position != index]
        if sum(others) / len(others) < threshold:
            return None, (422, {"code": "inconsistent_samples", "message": (
                "As fotos não parecem ser da mesma pessoa, ou variaram demais. Repita o "
                "cadastro com apenas uma pessoa, olhando para a câmera.")})
    return vectors, None


def ranked_scores(vector, candidates):
    """Melhor similaridade de cada dono de vetores, da maior para a menor."""
    return sorted(((max(cosine(vector, known) for known in vectors), owner)
                   for owner, vectors in candidates.items()), reverse=True)


class Recognition:
    def __init__(self, controller, identities, engine=None, settings=None):
        self.controller, self.identities = controller, identities
        self.engine = engine
        self.settings = settings or FaceSettings()
        self.failures: list[float] = []
        self.challenges: dict[str, Challenge] = {}

    # --- teste simulado ------------------------------------------------------------------

    def simulate(self, scenario: str, identity_id: int | None) -> tuple[int, dict]:
        with self.controller.mutex:
            if scenario == "no_match":
                message = "Rosto desconhecido no teste simulado. A trava permanece engatada."
                self.controller.record(Event(
                    "recognition_no_match", "Rosto desconhecido (simulado)", message,
                    "recognition", "denied",
                ))
                return 409, self._body(False, "no_match", message)
            decision = self.identities.decide(identity_id)
            reference = f"#{identity_id}"
            if not decision.allowed:
                self.controller.record(Event(
                    "recognition_denied", "Acesso recusado no teste de reconhecimento",
                    f"Identidade {reference}: {decision.message}", "recognition", "denied",
                ))
                return 409, self._body(False, decision.code, decision.message, identity_id)
            code, body = self.controller.recognition_release(reference)
            body.update(simulated=True, identity_id=identity_id)
            body.setdefault("code", "authorized")
            return code, body

    def _body(self, ok, code, message, identity_id=None, **extra):
        return {"ok": ok, "simulated": extra.pop("simulated", True), "code": code,
                "message": message, "identity_id": identity_id,
                "state": self.controller.status(), **extra}

    # --- reconhecimento facial real ------------------------------------------------------

    def status(self):
        engine = self.engine
        return {
            "available": bool(engine and engine.available),
            "reason": "" if engine and engine.available else (
                engine.reason if engine else "Motor facial não configurado."),
            "model": engine.model_id if engine else "nenhum",
            "match_threshold": self.settings.match_threshold,
            "ambiguity_margin": self.settings.ambiguity_margin,
            "liveness": {
                "required": True,
                "method": "head_turn",
                "front_max_yaw": self.settings.front_max_yaw,
                "turn_min_yaw": self.settings.turn_min_yaw,
            },
            "samples": {"min": MIN_SAMPLES, "max": MAX_SAMPLES},
            "stores_images": False,
        }

    def _require_engine(self):
        if self.engine is None or not self.engine.available:
            reason = self.engine.reason if self.engine else "Motor facial não configurado."
            raise FaceError("engine_unavailable", reason)

    def _scores(self, vector, candidates):
        """Melhor similaridade de cada identidade, da maior para a menor."""
        ranked = [(max(cosine(vector, known) for known in vectors), identity_id)
                  for identity_id, vectors in candidates.items()]
        return sorted(ranked, reverse=True)

    def challenge(self, session_id: str):
        """Cria um desafio de giro curto, de uso único, antes do reconhecimento da porta."""
        self._require_engine()
        with self.controller.mutex:
            wait = self._blocked_for()
            if wait > 0:
                return self._rate_limited(wait)
            now = self.identities.clock()
            self.challenges = {
                key: value for key, value in self.challenges.items()
                if value.expires_at > now and value.session_id != session_id
            }
            while len(self.challenges) >= self.settings.open_challenges:
                self.challenges.pop(next(iter(self.challenges)))
            token = secrets.token_urlsafe(18)
            direction = secrets.choice(("left", "right"))
            self.challenges[token] = Challenge(
                direction, now + self.settings.challenge_seconds, session_id,
            )
        return 200, {
            "challenge_id": token,
            "direction": direction,
            "instruction": (
                "Vire o rosto bem pouco para a sua "
                f"{DIRECTION_TEXT[direction]} e fique assim por um instante."
            ),
            "expires_in": self.settings.challenge_seconds,
        }

    def cancel_challenge(self, challenge_id: str, session_id: str):
        with self.controller.mutex:
            challenge = self.challenges.get(challenge_id)
            if challenge and challenge.session_id == session_id:
                self.challenges.pop(challenge_id)

    def enroll_face(self, identity_id: int, images: list[bytes], actor: str) -> tuple[int, dict]:
        """Valida as fotos e grava só os vetores. As imagens são descartadas."""
        self._require_engine()
        vectors, problem = validated_vectors(self.engine, images, self.settings.match_threshold)
        if problem:
            return problem
        threshold = self.settings.match_threshold
        with self.controller.mutex:
            others = self.identities.face_candidates(exclude=identity_id)
            for vector in vectors:
                ranked = self._scores(vector, others)
                if ranked and ranked[0][0] >= threshold:
                    return 409, {"code": "face_already_enrolled", "message": (
                        f"Este rosto já está cadastrado na identidade #{ranked[0][1]}. Exclua ou "
                        "ajuste a outra identidade antes de repetir o cadastro.")}
            public = self.identities.enroll_face(identity_id, vectors, self.engine.model_id, actor)
        return 201, {"identity": public,
                     "message": f"Cadastro facial registrado com {len(vectors)} amostras. "
                                "Nenhuma imagem foi guardada."}

    def _blocked_for(self) -> float:
        now = self.identities.clock()
        window = self.settings.failure_window_seconds
        self.failures = [moment for moment in self.failures if now - moment < window]
        if len(self.failures) < self.settings.failure_limit:
            return 0.0
        return window - (now - self.failures[0])

    def _deny_liveness(self, code, title, message):
        self.failures.append(self.identities.clock())
        self.controller.record(Event(code, title, message, "recognition", "denied"))
        return 409, self._body(False, code, message, simulated=False)

    def _rate_limited(self, wait):
        return 429, self._body(
            False, "rate_limited",
            f"Muitas tentativas sem reconhecimento. Aguarde {int(wait) + 1} segundos.",
            simulated=False,
        )

    def _expired_challenge(self):
        return 409, self._body(
            False, "challenge_expired",
            "O desafio de movimento expirou ou foi cancelado. Tente de novo.", simulated=False,
        )

    def verify(self, challenge_id: str, front: bytes, turned: list[bytes], *,
               session_id: str, authorize) -> tuple[int, dict]:
        """Confere movimento, reconhece o rosto e, se autorizado, libera a trava virtual."""
        self._require_engine()
        with self.controller.mutex:
            wait = self._blocked_for()
            if wait > 0:
                return self._rate_limited(wait)
            now = self.identities.clock()
            challenge = self.challenges.get(challenge_id)
            if (challenge is None or challenge.expires_at <= now or challenge.processing
                    or challenge.session_id != session_id):
                return self._expired_challenge()
            challenge = replace(challenge, processing=True)
            self.challenges[challenge_id] = challenge
        try:
            front_reading = self.engine.read(front)
            readings, last_error = [], None
            for image in turned[:self.settings.max_turned_frames]:
                try:
                    readings.append(self.engine.read(image))
                except FaceError as error:
                    if error.code == "engine_unavailable":
                        raise
                    last_error = error
            if not readings:
                raise last_error or FaceError("no_face", "Nenhum rosto foi encontrado.")
        except FaceError as error:
            with self.controller.mutex:
                if self.challenges.get(challenge_id) is challenge:
                    self.challenges.pop(challenge_id)
            if error.code == "engine_unavailable":
                raise
            # Problema de captura (sem rosto, borrado): não é tentativa de acesso.
            return 422, {"code": error.code, "message": error.message, "simulated": False}
        with self.controller.mutex, authorize():
            # A captura é processada sem a trava global. Revalide antes de atuar: uma
            # sessão pode ter sido revogada e o desafio pode ter vencido ou sido cancelado.
            if self.challenges.get(challenge_id) is not challenge:
                return self._expired_challenge()
            self.challenges.pop(challenge_id)
            if challenge.expires_at <= self.identities.clock():
                return self._expired_challenge()
            wait = self._blocked_for()
            if wait > 0:
                return self._rate_limited(wait)
            direction_sign = 1 if challenge.direction == "left" else -1
            moved = [
                reading for reading in readings
                if direction_sign * reading.yaw >= self.settings.turn_min_yaw
            ]
            if abs(front_reading.yaw) > self.settings.front_max_yaw or not moved:
                return self._deny_liveness(
                    "liveness_failed", "Movimento facial não confirmado",
                    "Não detectamos o movimento pedido. Comece de frente para a câmera e "
                    f"depois vire o rosto bem pouco para a sua "
                    f"{DIRECTION_TEXT[challenge.direction]}. A trava permanece engatada.",
                )
            candidates = self.identities.face_candidates()
            ranked = self._scores(front_reading.embedding, candidates)
            if not ranked:
                message = ("Nenhuma face está cadastrada ainda. Cadastre uma identidade com "
                           "rosto em Identidades.")
                self.controller.record(Event(
                    "recognition_no_match", "Nenhuma face cadastrada", message,
                    "recognition", "denied"))
                return 409, self._body(False, "no_faces_enrolled", message, simulated=False)
            best_score, best_id = ranked[0]
            second = ranked[1][0] if len(ranked) > 1 else -1.0
            settings = self.settings
            if best_id is None or best_score < settings.match_threshold:
                self.failures.append(self.identities.clock())
                message = ("Face não cadastrada. Este rosto não está no banco de identidades; "
                           "a trava permanece engatada.")
                self.controller.record(Event(
                    "recognition_no_match", "Face não cadastrada", message,
                    "recognition", "denied"))
                return 409, self._body(False, "no_match", message, simulated=False,
                                       similarity=round(best_score, 3))
            close_call = best_score - second < settings.ambiguity_margin
            if second >= settings.match_threshold and close_call:
                self.failures.append(self.identities.clock())
                message = "Rosto parecido com mais de uma identidade; por segurança, recusado."
                self.controller.record(Event(
                    "recognition_ambiguous", "Reconhecimento ambíguo", message,
                    "recognition", "denied"))
                return 409, self._body(False, "ambiguous", message, simulated=False)
            turned_worst = min(
                self._scores(reading.embedding, {best_id: candidates[best_id]})[0][0]
                for reading in readings
            )
            if turned_worst < settings.match_threshold - settings.turned_slack:
                return self._deny_liveness(
                    "face_changed", "Rosto mudou durante o desafio",
                    "O rosto da foto de frente não é o mesmo da foto virada. "
                    "A trava permanece engatada.",
                )
            reference = f"#{best_id}"
            decision = self.identities.decide(best_id)
            if not decision.allowed:
                self.controller.record(Event(
                    "recognition_denied", "Acesso recusado no reconhecimento facial",
                    f"Identidade {reference} reconhecida, mas recusada: {decision.message}",
                    "recognition", "denied"))
                return 409, self._body(False, decision.code, decision.message, best_id,
                                       simulated=False, similarity=round(best_score, 3))
            if challenge.expires_at <= self.identities.clock():
                return self._expired_challenge()
            def guard():
                # _sync pode salvar o cenário antes da atuação: revalide também depois
                # desse trabalho. Preserve a autoria do contexto externo ao reautenticar.
                actor = self.controller.actor
                try:
                    with authorize():
                        current = self.identities.decide(best_id)
                        if not current.allowed:
                            raise Denied(current.code, current.message)
                        if challenge.expires_at <= self.identities.clock():
                            raise Denied(
                                "challenge_expired",
                                "O desafio de movimento expirou. Tente de novo.",
                            )
                finally:
                    self.controller.actor = actor

            code, body = self.controller.recognition_release(
                reference, simulated=False, note=f" (similaridade {best_score:.2f})",
                guard=guard,
            )
            body.update(simulated=False, identity_id=best_id, similarity=round(best_score, 3))
            body.setdefault("code", "authorized")
            return code, body
