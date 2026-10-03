"""Cadastro do rosto da conta e entrada no aplicativo pelo rosto.

Entrar pelo rosto é autenticação, bem mais sensível que liberar uma porta virtual. Por isso:
a conta precisa escolher usar o rosto (senha de novo + consentimento); a entrada exige um
DESAFIO DE MOVIMENTO sorteado (virar o rosto para um lado), que uma foto parada não cumpre; o
limite de similaridade é mais rígido; e há bloqueio após falhas. Mesmo assim, o desafio é simples:
um vídeo ou uma foto girada podem enganá-lo. Veja docs/facial-recognition.md.
"""

import secrets
import threading
from dataclasses import dataclass, replace

from everlock.faces import FaceError
from everlock.recognition import ranked_scores, validated_vectors

CONSENT_VERSION = "2026-10-02"
CONSENT_TEXT = (
    "Concordo em cadastrar meu rosto para entrar neste aplicativo. As fotos são analisadas na "
    "memória e descartadas: apenas um vetor numérico do meu rosto (dado biométrico) é guardado, "
    "cifrado, neste computador. Posso remover meu rosto a qualquer momento e continuar entrando "
    "com e-mail ou usuário e senha. Sei que o reconhecimento facial pode errar."
)
NOT_ENROLLED = ("Face não cadastrada. Este rosto não está no banco de dados do EverLock. Entre "
                "com e-mail e senha e cadastre seu rosto em Conta.")
DIRECTION_TEXT = {"left": "esquerda", "right": "direita"}


@dataclass(frozen=True)
class LoginSettings:
    match_threshold: float = 0.55  # mais rígido que o da porta (0,45): aqui é autenticação
    ambiguity_margin: float = 0.08
    turned_slack: float = 0.10  # o rosto virado se parece menos; tolera até esta queda
    front_max_yaw: float = 0.15  # "de frente" = nariz perto do meio dos olhos
    turn_min_yaw: float = 0.22  # giro mínimo pedido pelo desafio
    challenge_seconds: float = 45.0
    open_challenges: int = 20
    failure_limit: int = 5
    failure_window_seconds: float = 120.0
    attempt_limit: int = 20
    attempt_window_seconds: float = 60.0
    max_turned_frames: int = 6


@dataclass(frozen=True)
class Challenge:
    direction: str
    expires_at: float
    processing: bool = False


class FaceLogin:
    def __init__(self, accounts, engine, vault, clock, settings=None):
        self.accounts, self.engine, self.vault = accounts, engine, vault
        self.clock, self.settings = clock, settings or LoginSettings()
        self.challenges: dict[str, Challenge] = {}
        self.failures: list[float] = []
        self.attempts: list[float] = []
        self.lock = threading.RLock()

    # --- estado ---------------------------------------------------------------------------

    def availability(self):
        engine_ok = bool(self.engine and self.engine.available)
        vault_ok = bool(self.vault and self.vault.available)
        if engine_ok and vault_ok:
            return {"available": True, "reason": ""}
        reason = (self.engine.reason if self.engine and not engine_ok
                  else "A biblioteca de cifra (cryptography) não está instalada.")
        return {"available": False, "reason": reason}

    def info(self, user_id):
        return {**self.availability(), **self.accounts.face_info(user_id),
                "consent": {"version": CONSENT_VERSION, "text": CONSENT_TEXT},
                "match_threshold": self.settings.match_threshold}

    def _require_engine(self):
        state = self.availability()
        if not state["available"]:
            raise FaceError("engine_unavailable", state["reason"])

    # --- cadastro do rosto da própria conta -----------------------------------------------

    def enroll(self, user, password, images, client, authorize):
        self._require_engine()
        self.accounts.confirm_password(user["username"], password, client)
        vectors, problem = validated_vectors(self.engine, images, self.settings.match_threshold)
        if problem:
            return problem
        with authorize() as user:
            others = self.accounts.face_vectors(self.vault, exclude=user["id"])
            for vector in vectors:
                ranked = ranked_scores(vector, others)
                if ranked and ranked[0][0] >= self.settings.match_threshold:
                    return 409, {"code": "face_already_enrolled", "message": (
                        "Este rosto já está cadastrado em outra conta. Cada rosto entra em uma "
                        "única conta.")}
            sealed = [self.vault.seal(user["id"], vector, "conta") for vector in vectors]
            self.accounts.save_face(user["id"], user["username"], sealed, self.engine.model_id,
                                    CONSENT_VERSION)
        return 201, {"message": (f"Rosto cadastrado com {len(sealed)} amostras. Nenhuma imagem "
                                 "foi guardada. Agora você pode entrar com o rosto."),
                     "face": self.accounts.face_info(user["id"])}

    # --- entrada pelo rosto ---------------------------------------------------------------

    def challenge(self):
        now = self.clock()
        with self.lock:
            self.challenges = {key: value for key, value in self.challenges.items()
                               if value.expires_at > now}
            while len(self.challenges) >= self.settings.open_challenges:
                self.challenges.pop(next(iter(self.challenges)))
            token = secrets.token_urlsafe(18)
            direction = secrets.choice(("left", "right"))
            self.challenges[token] = Challenge(direction, now + self.settings.challenge_seconds)
        return {"challenge_id": token, "direction": direction,
                "instruction": ("Vire o rosto bem pouco para a sua "
                                f"{DIRECTION_TEXT[direction]} e fique assim por um instante."),
                "expires_in": self.settings.challenge_seconds}

    def _blocked_for(self, now):
        s = self.settings
        self.failures = [t for t in self.failures if now - t < s.failure_window_seconds]
        self.attempts = [t for t in self.attempts if now - t < s.attempt_window_seconds]
        if len(self.failures) >= s.failure_limit:
            return s.failure_window_seconds - (now - self.failures[0])
        if len(self.attempts) >= s.attempt_limit:
            return s.attempt_window_seconds - (now - self.attempts[0])
        return 0.0

    def cancel_challenge(self, challenge_id):
        with self.lock:
            self.challenges.pop(challenge_id, None)

    def _expired_challenge(self):
        return 409, {"code": "challenge_expired",
                     "message": "O desafio expirou ou foi cancelado. Tente de novo."}, None

    def _fail(self, code, message, status=409):
        with self.lock:
            self.failures.append(self.clock())
        self.accounts.record("login_face_denied", None, f"Entrada pelo rosto recusada ({code}).")
        return status, {"code": code, "message": message}, None

    def login(self, challenge_id, front, turned):
        self._require_engine()
        s, now = self.settings, self.clock()
        with self.lock:
            wait = self._blocked_for(now)
            if wait > 0:
                return 429, {"code": "rate_limited", "message": (
                    f"Muitas tentativas. Aguarde {int(wait) + 1} segundos ou entre com a senha.")
                }, None
            self.attempts.append(now)
            challenge = self.challenges.get(challenge_id)
            if challenge is None or challenge.expires_at <= now or challenge.processing:
                return self._expired_challenge()
            challenge = replace(challenge, processing=True)
            self.challenges[challenge_id] = challenge
        try:
            front_reading = self.engine.read(front)
            readings, last_error = [], None
            for image in turned[:s.max_turned_frames]:
                try:
                    readings.append(self.engine.read(image))
                except FaceError as error:
                    if error.code == "engine_unavailable":
                        raise
                    last_error = error
            if not readings:
                raise last_error or FaceError("no_face", "Nenhum rosto foi encontrado.")
        except FaceError as error:
            with self.lock:
                if self.challenges.get(challenge_id) is challenge:
                    self.challenges.pop(challenge_id)
            if error.code == "engine_unavailable":
                raise
            return 422, {"code": error.code, "message": error.message}, None
        # Galeria e criação da sessão ficam na mesma trava das alterações de conta/rosto.
        # A leitura de imagens, mais demorada, permite cancelamento sem bloquear o servidor.
        with self.accounts.mutex, self.lock:
            if self.challenges.get(challenge_id) is not challenge:
                return self._expired_challenge()
            self.challenges.pop(challenge_id)
            if challenge.expires_at <= self.clock():
                return self._expired_challenge()
            candidates = self.accounts.face_vectors(self.vault)
            if not candidates:
                return 409, {"code": "no_faces_enrolled", "message": (
                    "Nenhuma face está cadastrada neste computador ainda. Entre com e-mail e "
                    "senha e cadastre seu rosto em Conta.")}, None
            direction_sign = 1 if challenge.direction == "left" else -1
            moved = [r for r in readings if direction_sign * r.yaw >= s.turn_min_yaw]
            if abs(front_reading.yaw) > s.front_max_yaw or not moved:
                return self._fail("liveness_failed", (
                    "Não detectamos o movimento pedido. Comece de frente para a câmera e depois "
                    f"vire o rosto bem pouco para a sua {DIRECTION_TEXT[challenge.direction]}."))
            ranked = ranked_scores(front_reading.embedding, candidates)
            best, user_id = ranked[0]
            second = ranked[1][0] if len(ranked) > 1 else -1.0
            if best < s.match_threshold:
                return self._fail("no_match", NOT_ENROLLED)
            if second >= s.match_threshold and best - second < s.ambiguity_margin:
                return self._fail("ambiguous", (
                    "Rosto parecido com mais de uma conta; por segurança, recusado. "
                    "Entre com a senha."))
            turned_worst = min(
                ranked_scores(reading.embedding, {user_id: candidates[user_id]})[0][0]
                for reading in readings
            )
            if turned_worst < s.match_threshold - s.turned_slack:
                return self._fail("face_changed", (
                    "O rosto da foto de frente não é o mesmo da foto virada. Tente de novo."))
            if challenge.expires_at <= self.clock():
                return self._expired_challenge()
            token = self.accounts.login_by_face(user_id)
            if challenge.expires_at <= self.clock():
                # O banco pode ter demorado ao criar a sessão. Não entregue um cookie
                # quando o desafio já venceu; ninguém vê o token antes desta decisão.
                self.accounts.logout(token)
                return self._expired_challenge()
            self.failures.clear()
        return 200, {"message": "Rosto reconhecido. Sessão iniciada."}, token
