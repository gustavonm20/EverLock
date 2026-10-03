"""Avaliação facial local 1:N; não altera cadastros nem configurações do aplicativo."""

import hashlib
import json
import math
import re
from pathlib import Path
from time import perf_counter

from everlock.face_login import LoginSettings
from everlock.faces import MAX_IMAGE_BYTES, FaceEngine, FaceError
from everlock.recognition import (
    MAX_SAMPLES,
    MIN_SAMPLES,
    FaceSettings,
    ranked_scores,
    validated_vectors,
)


class ManifestError(ValueError):
    """Conjunto sem consentimento ou inadequado para uma avaliação separada."""


def _manifest(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or set(data) != {"version", "subjects"}:
        raise ManifestError("O manifesto deve conter somente version e subjects.")
    if type(data["version"]) is not int or data["version"] != 1:
        raise ManifestError("Versão de manifesto não suportada; use version: 1.")
    if not isinstance(data["subjects"], list) or not data["subjects"]:
        raise ManifestError("Informe pelo menos uma pessoa no manifesto.")
    root, codes, seen, subjects = path.resolve().parent, set(), set(), []
    for item in data["subjects"]:
        if not isinstance(item, dict) or set(item) != {"code", "consent", "enrollment", "tests"}:
            raise ManifestError("Cada pessoa exige code, consent, enrollment e tests.")
        code = item["code"]
        if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", code):
            raise ManifestError("Use códigos anônimos de até 32 letras, números, _ ou -.")
        if code in codes:
            raise ManifestError("Cada pessoa deve ter um código diferente.")
        if item["consent"] is not True:
            raise ManifestError("Todas as pessoas precisam autorizar esta avaliação.")
        codes.add(code)
        subject = {"code": code}
        for stage in ("enrollment", "tests"):
            names = item[stage]
            if not isinstance(names, list) or (stage == "tests" and not names):
                raise ManifestError("enrollment e tests são listas; tests não pode ficar vazio.")
            if stage == "enrollment" and names and not MIN_SAMPLES <= len(names) <= MAX_SAMPLES:
                raise ManifestError(f"O cadastro exige de {MIN_SAMPLES} a {MAX_SAMPLES} imagens.")
            paths = []
            for name in names:
                if not isinstance(name, str) or not name or Path(name).is_absolute():
                    raise ManifestError("Use caminhos relativos à pasta do manifesto.")
                image = (root / name).resolve()
                if not image.is_relative_to(root) or image.suffix.lower() not in {
                    ".jpg", ".jpeg", ".png",
                }:
                    raise ManifestError("Use JPEG/PNG dentro da pasta do manifesto.")
                if image in seen:
                    raise ManifestError("Cada imagem pode aparecer uma única vez no conjunto.")
                seen.add(image)
                paths.append(image)
            subject[stage] = paths
        subjects.append(subject)
    if not any(subject["enrollment"] for subject in subjects):
        raise ManifestError("Inclua pelo menos uma pessoa com imagens de cadastro.")
    return subjects


def _images(subjects: list[dict]) -> dict:
    """Lê sem copiar arquivos; detecta cópias idênticas mesmo com outro nome."""
    images, digests = {}, set()
    for subject in subjects:
        for stage in ("enrollment", "tests"):
            for index, path in enumerate(subject[stage], 1):
                key = subject["code"], stage, index
                try:
                    with path.open("rb") as handle:
                        image = handle.read(MAX_IMAGE_BYTES + 1)
                except OSError:
                    images[key] = FaceError("file_unreadable", "Arquivo não pôde ser lido.")
                    continue
                if len(image) > MAX_IMAGE_BYTES:
                    images[key] = FaceError("invalid_image", "Imagem grande demais.")
                    continue
                digest = hashlib.sha256(image).digest()
                if digest in digests:
                    raise ManifestError(
                        "Há arquivos com conteúdo idêntico. Separe capturas distintas de "
                        "cadastro e teste, sem repetir imagens.")
                digests.add(digest)
                images[key] = image
    return images


def _elapsed_ms(timer, started):
    return max(0.0, (timer() - started) * 1000)


def _read(engine, image, key, captures, timer):
    code, stage, index = key
    result = {"subject": code, "stage": stage, "sample": index}
    started = timer()
    try:
        if isinstance(image, FaceError):
            raise image
        reading = engine.read(image)
    except FaceError as error:
        if error.code == "engine_unavailable":
            raise
        captures.append({**result, "code": error.code,
                         "engine_ms": _elapsed_ms(timer, started)})
        raise
    captures.append({**result, "code": "ok", "engine_ms": _elapsed_ms(timer, started),
                     "quality": {
        "face_pixels": reading.face_pixels, "detection_score": reading.detection_score,
        "sharpness": reading.sharpness, "yaw": reading.yaw,
    }})
    return reading


class _EnrollmentReader:
    """Reutiliza a validação de cadastro real registrando as falhas por amostra."""

    def __init__(self, engine, samples, captures, timer):
        self.engine, self.samples, self.captures = engine, iter(samples), captures
        self.timer = timer

    def read(self, image):
        key, value = next(self.samples)
        return _read(self.engine, value, key, self.captures, self.timer)


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _latency_summary(values):
    ordered = sorted(values)
    return {
        "count": len(ordered),
        "mean": sum(ordered) / len(ordered) if ordered else None,
        "p95": ordered[math.ceil(0.95 * len(ordered)) - 1] if ordered else None,
        "min": ordered[0] if ordered else None,
        "max": ordered[-1] if ordered else None,
    }


def evaluate(
    manifest: Path, engine: FaceEngine, *, profile: str = "door",
    threshold: float | None = None, ambiguity_margin: float | None = None,
    timer=perf_counter,
) -> dict:
    """Compara cada captura de teste com a galeria inteira, como o reconhecimento real.

    As taxas se referem somente à identificação, antes de giro e autorização. Falhas de
    captura e cadastros recusados são separados dos denominadores de identificação.
    """
    if profile not in {"door", "login"}:
        raise ManifestError("Perfil deve ser door ou login.")
    settings = FaceSettings() if profile == "door" else LoginSettings()
    threshold = settings.match_threshold if threshold is None else threshold
    margin = settings.ambiguity_margin if ambiguity_margin is None else ambiguity_margin
    if not 0 <= threshold <= 1 or not 0 <= margin <= 1:
        raise ManifestError("Limite e margem devem ficar entre 0 e 1.")
    subjects = _manifest(Path(manifest))
    images = _images(subjects)
    if not engine.available:
        raise FaceError("engine_unavailable", engine.reason)
    captures, enrollments, gallery = [], [], {}
    for subject in subjects:
        code = subject["code"]
        if not subject["enrollment"]:
            continue
        samples = [((code, "enrollment", index), images[code, "enrollment", index])
                   for index in range(1, len(subject["enrollment"]) + 1)]
        started = timer()
        reader = _EnrollmentReader(engine, samples, captures, timer)
        vectors, problem = validated_vectors(reader, [b""] * len(samples), threshold)
        status = problem[1]["code"] if problem else "enrolled"
        if vectors:
            for vector in vectors:
                scores = ranked_scores(vector, gallery)
                if scores and scores[0][0] >= threshold:
                    status = "face_already_enrolled"
                    break
            if status == "enrolled":
                gallery[code] = vectors
        enrollments.append({"subject": code, "code": status,
                            "latency_ms": _elapsed_ms(timer, started)})

    attempts = []
    counts = dict.fromkeys((
        "genuine_attempts", "genuine_correct", "genuine_rejected", "genuine_misidentified",
        "unknown_attempts", "unknown_false_acceptances", "unknown_correct_rejections",
        "genuine_capture_failures", "unknown_capture_failures", "skipped_tests",
    ), 0)
    for subject in subjects:
        code, genuine = subject["code"], bool(subject["enrollment"])
        for index in range(1, len(subject["tests"]) + 1):
            attempt = {"subject": code, "sample": index,
                       "kind": "genuine" if genuine else "unknown"}
            if not gallery or (genuine and code not in gallery):
                reason = "no_gallery" if not gallery else "enrollment_failed"
                attempts.append({**attempt, "code": reason})
                counts["skipped_tests"] += 1
                continue
            started = timer()
            try:
                reading = _read(engine, images[code, "tests", index],
                                (code, "tests", index), captures, timer)
            except FaceError as error:
                counts["genuine_capture_failures" if genuine else "unknown_capture_failures"] += 1
                attempts.append({**attempt, "code": "capture_failed", "reason": error.code,
                                 "latency_ms": _elapsed_ms(timer, started)})
                continue
            ranked = ranked_scores(reading.embedding, gallery)
            best, candidate = ranked[0]
            second = ranked[1][0] if len(ranked) > 1 else -1.0
            verdict = "matched"
            if best < threshold:
                verdict = "no_match"
            elif second >= threshold and best - second < margin:
                verdict = "ambiguous"
            accepted = verdict == "matched"
            counts["genuine_attempts" if genuine else "unknown_attempts"] += 1
            if genuine:
                outcome = ("genuine_correct" if accepted and candidate == code else
                           "genuine_misidentified" if accepted else "genuine_rejected")
            else:
                outcome = "unknown_false_acceptances" if accepted else "unknown_correct_rejections"
            counts[outcome] += 1
            attempts.append({**attempt, "code": verdict,
                             "candidate": candidate if accepted else None,
                             "best_similarity": best, "second_similarity": second,
                             "outcome": outcome, "latency_ms": _elapsed_ms(timer, started)})

    genuine, unknown = counts["genuine_attempts"], counts["unknown_attempts"]
    return {
        "report_version": 1, "scope": "offline_1_to_n_identification",
        "model": engine.model_id, "profile": profile, "provisional": True,
        "settings": {"match_threshold": threshold, "ambiguity_margin": margin,
                     "front_max_yaw": settings.front_max_yaw,
                     "turn_min_yaw": settings.turn_min_yaw},
        "gallery": {"subjects": len(gallery), "samples": sum(map(len, gallery.values()))},
        "enrollments": enrollments, "counts": counts,
        "rates": {
            "false_acceptance_rate": _rate(counts["unknown_false_acceptances"], unknown),
            "false_rejection_rate": _rate(counts["genuine_rejected"], genuine),
            "false_identification_rate": _rate(counts["genuine_misidentified"], genuine),
            "genuine_failure_rate": _rate(
                counts["genuine_rejected"] + counts["genuine_misidentified"], genuine),
            "correct_identification_rate": _rate(counts["genuine_correct"], genuine),
        },
        "captures": captures, "attempts": attempts,
        "latency": {
            "unit": "milliseconds",
            "identification": _latency_summary([
                attempt["latency_ms"] for attempt in attempts if "outcome" in attempt
            ]),
        },
        "limitations": [
            "Limites provisórios; este relatório não altera a configuração do aplicativo.",
            "Uma captura de teste é uma tentativa 1:N, não um conjunto de pares independentes.",
            "Falhas de captura e cadastros recusados não entram nas taxas de identificação.",
            "Não mede desafio de movimento, prova de vida, autorização, sessões ou liberação.",
            "Latência mede motor e comparação; não inclui arquivos, câmera, rede ou modelos.",
            "Zero erros numa amostra pequena não demonstra precisão em outras pessoas.",
            "Cópias idênticas são recusadas; recortes da mesma captura exigem revisão humana.",
        ],
    }
