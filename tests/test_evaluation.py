import json
import math
import runpy
import tracemalloc
from pathlib import Path

import pytest

from everlock.evaluation import ManifestError, check_dataset, evaluate
from everlock.faces import FaceError, FaceReading, UnavailableEngine


def vector(x=0.0, y=0.0, z=0.0):
    return (x, y, z, *([0.0] * 125))


class Engine:
    available, reason, model_id = True, "", "synthetic-test-only"

    def __init__(self):
        self.readings, self.calls = {}, 0

    def read(self, image):
        self.calls += 1
        result = self.readings[image]
        if isinstance(result, FaceError):
            raise result
        return FaceReading(result, 100, 0.99, 100.0, 0.02)


def dataset(tmp_path, definitions):
    engine, subjects = Engine(), []
    for code, enrollment, tests in definitions:
        subject = {"code": code, "consent": True}
        for stage, readings in (("enrollment", enrollment), ("tests", tests)):
            subject[stage] = []
            for index, reading in enumerate(readings, 1):
                name = f"{code}-{stage}-{index}.png"
                image = f"synthetic:{name}".encode()
                (tmp_path / name).write_bytes(image)
                engine.readings[image] = reading
                subject[stage].append(name)
        subjects.append(subject)
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"version": 1, "subjects": subjects}), encoding="utf-8")
    return path, engine


def test_one_to_many_rates_separate_wrong_identity_capture_and_ambiguity(tmp_path):
    a, b, other = vector(1), vector(y=1), vector(z=1)
    ambiguous = vector(math.sqrt(0.5), math.sqrt(0.5))
    bad = FaceError("no_face", "Não há rosto.")
    path, engine = dataset(tmp_path, [
        ("p001", [a] * 3, [a, other, b, bad]),
        ("p002", [b] * 3, [bad]),
        ("p003", [], [a, other, ambiguous, bad]),
    ])
    report = evaluate(path, engine)
    assert report["gallery"] == {"subjects": 2, "samples": 6}
    assert report["counts"] == {
        "genuine_attempts": 3, "genuine_correct": 1, "genuine_rejected": 1,
        "genuine_misidentified": 1, "unknown_attempts": 3,
        "unknown_false_acceptances": 1, "unknown_correct_rejections": 2,
        "genuine_capture_failures": 2, "unknown_capture_failures": 1, "skipped_tests": 0,
    }
    assert report["rates"] == pytest.approx({
        "false_acceptance_rate": 1 / 3, "false_rejection_rate": 1 / 3,
        "false_identification_rate": 1 / 3, "genuine_failure_rate": 2 / 3,
        "correct_identification_rate": 1 / 3,
    })
    assert report["attempts"][-2]["code"] == "ambiguous"
    assert len(report["captures"]) == engine.calls == 15
    encoded = json.dumps(report)
    for sensitive in (str(tmp_path), ".png", "embedding", "synthetic:p001", "sha256"):
        assert sensitive not in encoded


def test_profiles_and_explicit_trial_limits_do_not_change_defaults(tmp_path):
    a, near = vector(1), vector(0.5, math.sqrt(0.75))
    path, engine = dataset(tmp_path, [("p001", [a] * 3, [near])])
    door, login = evaluate(path, engine), evaluate(path, engine, profile="login")
    trial = evaluate(path, engine, profile="login", threshold=0.45, ambiguity_margin=0.02)
    assert door["counts"]["genuine_correct"] == trial["counts"]["genuine_correct"] == 1
    assert login["counts"]["genuine_rejected"] == 1
    assert login["settings"]["match_threshold"] == 0.55
    assert evaluate(path, engine, profile="login")["settings"]["match_threshold"] == 0.55
    assert door["rates"]["false_acceptance_rate"] is None


def test_failed_enrollment_tests_are_skipped_not_treated_as_unknown(tmp_path):
    a, b = vector(1), vector(y=1)
    bad = FaceError("blurry", "Borrado.")
    path, engine = dataset(tmp_path, [
        ("p001", [a, a, bad], [b]),
        ("p002", [b] * 3, [b]),
    ])
    report = evaluate(path, engine)
    assert report["enrollments"][0]["code"] == "not_enough_samples"
    assert report["attempts"][0]["code"] == "enrollment_failed"
    assert report["counts"]["skipped_tests"] == 1
    assert report["counts"]["unknown_attempts"] == 0
    assert report["counts"]["genuine_attempts"] == 1
    assert report["rates"]["false_acceptance_rate"] is None
    assert engine.calls == 7


def test_enrollment_uses_consistency_and_duplicate_face_rules(tmp_path):
    a, b = vector(1), vector(y=1)
    path, engine = dataset(tmp_path, [
        ("p001", [a, a, b], [a]),
        ("p002", [b] * 3, [b]),
        ("p003", [b] * 3, [b]),
    ])
    report = evaluate(path, engine)
    assert [row["code"] for row in report["enrollments"]] == [
        "inconsistent_samples", "enrolled", "face_already_enrolled",
    ]
    assert report["gallery"]["subjects"] == 1
    assert report["counts"]["skipped_tests"] == 2


def test_no_usable_gallery_has_null_rates_and_capture_diagnostics(tmp_path):
    bad = FaceError("no_face", "Não há rosto.")
    path, engine = dataset(tmp_path, [("p001", [bad] * 3, [vector(1)])])
    report = evaluate(path, engine)
    assert report["gallery"]["subjects"] == 0
    assert all(value is None for value in report["rates"].values())
    assert report["attempts"][0]["code"] == "no_gallery"
    assert len(report["captures"]) == 3


@pytest.mark.parametrize("change", ["consent", "same_path", "escaped_path", "same_content"])
def test_manifest_rejects_unauthorized_or_leaking_dataset_before_reading_faces(tmp_path, change):
    path, engine = dataset(tmp_path, [("p001", [vector(1)] * 3, [vector(1)])])
    data = json.loads(path.read_text())
    subject = data["subjects"][0]
    if change == "consent":
        subject["consent"] = False
    elif change == "same_path":
        subject["tests"] = subject["enrollment"][:1]
    elif change == "escaped_path":
        subject["tests"] = ["../outside.png"]
    else:
        (tmp_path / subject["tests"][0]).write_bytes(
            (tmp_path / subject["enrollment"][0]).read_bytes())
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ManifestError):
        evaluate(path, engine)
    assert engine.calls == 0


def test_missing_test_file_is_a_capture_failure_and_unavailable_engine_is_an_error(tmp_path):
    path, engine = dataset(tmp_path, [("p001", [vector(1)] * 3, [vector(1)])])
    (tmp_path / "p001-tests-1.png").unlink()
    report = evaluate(path, engine)
    assert report["counts"]["genuine_capture_failures"] == 1
    assert report["counts"]["genuine_attempts"] == 0
    assert report["rates"]["false_rejection_rate"] is None
    assert report["attempts"][0]["reason"] == "file_unreadable"
    with pytest.raises(FaceError) as error:
        evaluate(path, UnavailableEngine("sem modelos"))
    assert error.value.code == "engine_unavailable"


def test_latency_has_monotonic_per_capture_attempt_and_summary_measurements(tmp_path):
    path, engine = dataset(tmp_path, [("p001", [vector(1)] * 3, [vector(1)])])
    ticks = iter(index / 1000 for index in range(30))
    report = evaluate(path, engine, timer=lambda: next(ticks))
    assert all(capture["engine_ms"] == pytest.approx(1) for capture in report["captures"])
    assert report["attempts"][0]["latency_ms"] == pytest.approx(3)
    assert report["latency"]["identification"] == pytest.approx({
        "count": 1, "mean": 3, "p95": 3, "min": 3, "max": 3,
    })
    assert report["enrollments"][0]["latency_ms"] > 0


def test_cli_writes_a_new_report_and_refuses_to_overwrite_it(tmp_path, monkeypatch, capsys):
    path, engine = dataset(tmp_path, [("p001", [vector(1)] * 3, [vector(1)])])
    script = Path(__file__).resolve().parents[1] / "scripts" / "avaliar_rostos.py"
    main = runpy.run_path(str(script))["main"]
    monkeypatch.setitem(main.__globals__, "OpenCVFaceEngine", lambda models: engine)
    output = tmp_path / "report.json"
    arguments = [str(path), "--output", str(output)]
    assert main(arguments) == 0
    original = output.read_text(encoding="utf-8")
    assert json.loads(original)["counts"]["genuine_correct"] == 1
    calls = engine.calls
    assert main(arguments) == 1
    assert engine.calls == calls  # não reprocessa as fotos para um destino já ocupado
    assert output.read_text(encoding="utf-8") == original
    assert "Avaliação não realizada" in capsys.readouterr().err


def test_preflight_cli_checks_files_without_loading_models(tmp_path, monkeypatch, capsys):
    path, _ = dataset(tmp_path, [("p001", [vector(1)] * 3, [vector(1)])])
    script = Path(__file__).resolve().parents[1] / "scripts" / "avaliar_rostos.py"
    main = runpy.run_path(str(script))["main"]

    def forbidden(models):
        raise AssertionError("A conferência não deve carregar modelos nem processar rostos.")

    monkeypatch.setitem(main.__globals__, "OpenCVFaceEngine", forbidden)
    assert main([str(path), "--check-only"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["ready"] is True
    assert report["files"] == {"total": 4, "readable": 4, "failed": 0}
    assert report["dataset"] == {
        "subjects": 1, "gallery_subjects": 1, "unknown_subjects": 0,
        "enrollment_images": 3, "test_images": 1,
    }
    assert report["warnings"]
    assert str(tmp_path) not in json.dumps(report)
    assert ".png" not in json.dumps(report)
    (tmp_path / "p001-tests-1.png").unlink()
    assert main([str(path), "--check-only"]) == 1
    failed = json.loads(capsys.readouterr().out)
    assert failed["problems"] == [{
        "subject": "p001", "stage": "tests", "sample": 1, "code": "file_unreadable",
    }]


def test_preflight_rejects_copies_and_reports_oversized_files(tmp_path):
    path, _ = dataset(tmp_path, [("p001", [vector(1)] * 3, [vector(1)])])
    test = tmp_path / "p001-tests-1.png"
    test.write_bytes((tmp_path / "p001-enrollment-1.png").read_bytes())
    with pytest.raises(ManifestError):
        check_dataset(path)
    test.write_bytes(b"x" * 1_500_001)
    report = check_dataset(path)
    assert not report["ready"]
    assert report["files"]["failed"] == 1
    assert report["problems"][0]["code"] == "invalid_image"


@pytest.mark.parametrize("change", ["replace", "remove"])
def test_changed_dataset_aborts_without_writing_a_report(tmp_path, monkeypatch, capsys, change):
    path, engine = dataset(tmp_path, [("p001", [vector(1)] * 3, [vector(1)])])
    original_read = engine.read

    def changing(image):
        reading = original_read(image)
        if engine.calls == 1:
            target = tmp_path / "p001-tests-1.png"
            if change == "replace":
                target.write_bytes(b"outra captura")
            else:
                target.unlink()
        return reading

    monkeypatch.setattr(engine, "read", changing)
    script = Path(__file__).resolve().parents[1] / "scripts" / "avaliar_rostos.py"
    main = runpy.run_path(str(script))["main"]
    monkeypatch.setitem(main.__globals__, "OpenCVFaceEngine", lambda models: engine)
    output = tmp_path / "result.json"
    assert main([str(path), "--output", str(output)]) == 1
    assert "conjunto mudou" in capsys.readouterr().err
    assert not output.exists()
    assert engine.calls == 3  # a captura de teste alterada não chegou ao motor


def test_large_dataset_does_not_keep_all_encoded_photos_in_memory(tmp_path, monkeypatch):
    path, engine = dataset(tmp_path, [("p001", [vector(1)] * 3, [vector(1)] * 24)])
    manifest = json.loads(path.read_text())
    for index, name in enumerate(manifest["subjects"][0]["enrollment"]
                                 + manifest["subjects"][0]["tests"]):
        (tmp_path / name).write_bytes(bytes([index]) + b"x" * 1_000_000)
    monkeypatch.setattr(engine, "read", lambda image: FaceReading(vector(1), 100, .99, 100, 0))
    tracemalloc.start()
    try:
        report = evaluate(path, engine)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert report["counts"]["genuine_correct"] == 24
    assert peak < 8_000_000  # fotos do conjunto somam 27 MB, sem contar o OpenCV
