"""Reconhecimento facial -> autorização no servidor -> trava virtual, de ponta a ponta.

Todos os testes são automatizados e offline. As "imagens" são textos sintéticos lidos pelo
FakeFaceEngine (dublê de teste explícito) ou quadros gerados por código para o motor OpenCV real.
Nenhuma pessoa, foto humana ou câmera física participa. Estes testes comprovam a ligação entre
reconhecimento, autorização e atuação; NÃO medem precisão facial, desempenho de câmera real ou
resistência a ataques de apresentação (prova de vida).
"""

import base64
import os
import re
from pathlib import Path

import pytest
from fakes import FakeFaceEngine
from fastapi.testclient import TestClient

import everlock
from everlock.app import create_app
from everlock.faces import OpenCVFaceEngine, UnavailableEngine
from everlock.identities import CONSENT_VERSION

EPOCH = 1_790_000_000.0
ADMIN = {"username": "operador", "email": "operador@example.com", "password": "Senha de testes1!"}
PERSON = {"username": "titular", "email": "titular@example.com", "password": "Titular de teste2@"}
JSON = {"Content-Type": "application/json"}


def b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


class Lab:
    """Aplicação isolada: relógio virtual da porta e relógio real das sessões controlados."""

    def __init__(self, tmp_path, engine=None):
        self.mono, self.wall = [100.0], [EPOCH]
        self.engine = engine or FakeFaceEngine()
        self.app = create_app(tmp_path / "acesso.sqlite3", clock=lambda: self.mono[0],
                              session_clock=lambda: self.wall[0], face_engine=self.engine)

    def __enter__(self):
        self.operator = TestClient(self.app, base_url="http://localhost").__enter__()
        assert self.operator.post("/api/auth/setup", json=ADMIN).status_code == 201
        self.login(self.operator, ADMIN)
        created = self.operator.post("/api/auth/users", json={**PERSON, "role": "user"})
        assert created.status_code == 201, created.text
        self.person_id = next(item["id"] for item in self.operator.get("/api/auth/users")
                              .json()["items"] if item["username"] == PERSON["username"])
        self.person = TestClient(self.app, base_url="http://localhost")
        self.login(self.person, PERSON)
        return self

    def __exit__(self, *exc):
        self.operator.__exit__(*exc)

    @staticmethod
    def login(client, who):
        reply = client.post("/api/auth/login", json={"identifier": who["username"],
                                                     "password": who["password"]})
        assert reply.status_code == 200, reply.text

    # --- passos do fluxo ------------------------------------------------------------------

    def create_identity(self, label="Titular 01", link=True, **extra):
        body = {"label": label, "consent": True, "consent_version": CONSENT_VERSION, **extra}
        if link:
            body["account_id"] = self.person_id
        reply = self.operator.post("/api/identities", json=body)
        assert reply.status_code == 201, reply.text
        return reply.json()

    def self_enroll(self, person="titular"):
        consent = self.person.post("/api/me/door-access/consent",
                                   json={"accepted": True, "version": CONSENT_VERSION})
        assert consent.status_code == 200, consent.text
        reply = self.person.post("/api/me/door-access/face", json={
            "password": PERSON["password"],
            "images": [b64(f"PESSOA:{person}:{n}") for n in range(5)],
        })
        assert reply.status_code == 201, reply.text
        return reply.json()

    def access_point(self, person="titular", *, front=None, turned=None):
        """O operador do ponto de acesso pede o desafio e envia as capturas sintéticas."""
        challenge = self.operator.post("/api/recognition/challenge", json={})
        if challenge.status_code != 200:
            return challenge
        challenge = challenge.json()
        sign = 1 if challenge["direction"] == "left" else -1
        body = {
            "challenge_id": challenge["challenge_id"],
            "front": b64(front or f"PESSOA:{person}:frente:0.0"),
            # O giro sempre acompanha o lado sorteado; `turned` é só o prefixo da pessoa.
            "turned": [b64(f"{turned or f'PESSOA:{person}:giro'}{n}:{sign * 0.3}")
                       for n in range(3)],
        }
        return self.operator.post("/api/recognition/verify", json=body)

    def door(self):
        return self.operator.get("/api/status").json()["door"]

    def events(self, limit=30):
        return self.operator.get(f"/api/events?limit={limit}").json()["items"]

    def recognition_events(self):
        return self.operator.get("/api/events?source=recognition&limit=50").json()["items"]


@pytest.fixture
def lab(tmp_path):
    with Lab(tmp_path) as running:
        yield running


# --- 1. fluxo autorizado completo ------------------------------------------------------------


def test_self_enrolled_face_releases_then_relocks_the_virtual_lock(lab):
    identity = lab.create_identity()
    view = lab.person.get("/api/me/door-access").json()
    assert view["linked"] and view["identity"]["id"] == identity["id"]
    assert view["identity"]["state"] == "not_enrolled"
    assert view["engine"]["available"] and view["engine"]["kind"] == "test_double"

    enrolled = lab.self_enroll()
    assert enrolled["access"]["identity"]["face_samples"] == 5
    assert enrolled["access"]["identity"]["consent"]["subject_method"] == "own_account"
    assert enrolled["access"]["identity"]["access_now"]["allowed"] is True

    assert lab.door()["lock"] == "engaged"
    granted = lab.access_point()
    body = granted.json()
    assert granted.status_code == 200, granted.text
    assert body["decision"] == {"granted": True, "code": "authorized", "title": "Acesso liberado",
                                "lock": "released", "release_seconds": 3.0}
    assert body["identity_id"] == identity["id"] and body["simulated"] is False
    assert body["state"]["door"]["lock"] == "released"
    assert body["state"]["door"]["position"] == "closed"  # liberar não abre a porta

    # Regras e tempo existentes: três segundos virtuais e volta automática à trava engatada.
    lab.mono[0] += 2.9
    assert lab.door()["lock"] == "released"
    lab.mono[0] += 0.2
    door = lab.door()
    assert door["lock"] == "engaged" and door["secured"] is True

    kinds = [event["type"] for event in lab.events()]
    assert kinds.index("release_expired") < kinds.index("unlock")  # mais recente primeiro
    unlock = next(event for event in lab.events() if event["type"] == "unlock")
    assert unlock["source"] == "recognition" and unlock["outcome"] == "success"
    assert f"#{identity['id']}" in unlock["detail"] and "Titular 01" not in unlock["detail"]


def test_entry_after_face_release_and_immediate_manual_lock(lab):
    lab.create_identity()
    lab.self_enroll()
    assert lab.access_point().status_code == 200
    # Travar agora: o operador encerra a liberação imediatamente, sem esperar o prazo.
    locked = lab.operator.post("/api/actions", json={"action": "end_release"})
    assert locked.status_code == 200 and locked.json()["state"]["door"]["secured"] is True
    assert lab.operator.post("/api/actions", json={"action": "open"}).json()["code"] == \
        "door_locked"

    # Nova liberação: abrir dentro do prazo, fechar depois e a trava volta a engatar.
    assert lab.access_point().status_code == 200
    assert lab.operator.post("/api/actions", json={"action": "open"}).status_code == 200
    lab.mono[0] += 3.5
    assert lab.door()["lock"] == "pending_close"
    assert lab.operator.post("/api/actions", json={"action": "close"}).status_code == 200
    assert lab.door()["secured"] is True


# --- 2. toda recusa mantém a trava engatada e fica no histórico ----------------------------


def _assert_denied(lab, response, code, status=409):
    body = response.json()
    assert response.status_code == status, response.text
    assert body["code"] == code
    assert body["decision"]["granted"] is False and body["decision"]["lock"] == "engaged"
    door = lab.door()
    assert door["lock"] == "engaged" and door["secured"] is True
    assert not any(event["type"] == "unlock" for event in lab.events(100))


@pytest.mark.parametrize("setup,code", [
    ("unknown", "no_match"),
    ("revoked", "no_faces_enrolled"),
    ("inactive_identity", "identity_inactive"),
    ("inactive_account", "account_inactive"),
    ("outside_schedule", "outside_schedule"),
])
def test_unauthorized_recognitions_never_release(lab, setup, code):
    identity = lab.create_identity()
    lab.self_enroll()
    person = "titular"
    if setup == "unknown":
        person = "desconhecido"
    elif setup == "revoked":
        assert lab.person.post("/api/me/door-access/revoke", json={}).status_code == 200
    elif setup == "inactive_identity":
        assert lab.operator.patch(f"/api/identities/{identity['id']}",
                                  json={"active": False}).status_code == 200
    elif setup == "inactive_account":
        assert lab.operator.patch(f"/api/auth/users/{lab.person_id}",
                                  json={"role": "user", "active": False}).status_code == 200
    elif setup == "outside_schedule":
        from datetime import datetime
        today = datetime.fromtimestamp(lab.wall[0]).weekday()
        other = [(today + 3) % 7]
        assert lab.operator.patch(f"/api/identities/{identity['id']}", json={
            "days": other, "start": "08:00", "end": "09:00"}).status_code == 200
    _assert_denied(lab, lab.access_point(person), code)
    assert lab.recognition_events()[0]["outcome"] == "denied"


def test_expired_retention_purges_the_face_and_denies(lab):
    lab.create_identity(retention_days=1)
    lab.self_enroll()
    lab.wall[0] += 86_400 + 1
    Lab.login(lab.operator, ADMIN)  # a sessão de oito horas também venceu
    _assert_denied(lab, lab.access_point(), "no_faces_enrolled")
    assert lab.person.get("/api/me/door-access").status_code == 401  # sessão da pessoa venceu


def test_ambiguous_and_low_quality_captures_are_denied_and_logged(lab):
    lab.create_identity()
    lab.self_enroll()
    other = lab.create_identity("Outra 02", link=False)
    assert lab.operator.post(f"/api/identities/{other['id']}/consent/confirm", json={
        "accepted": True, "version": CONSENT_VERSION}).status_code == 200
    assert lab.operator.post(f"/api/identities/{other['id']}/face", json={
        "images": [b64(f"PESSOA:outra:{n}") for n in range(5)]}).status_code == 201

    _assert_denied(lab, lab.access_point(front="MISTURA:titular:outra:1",
                                         turned="PESSOA:titular:giro"), "ambiguous")
    for capture, code in (("SEMROSTO", "no_face"), ("BORRADO", "blurry"),
                          ("DOISROSTOS", "multiple_faces"), ("lixo", "invalid_image")):
        _assert_denied(lab, lab.access_point(front=capture), code, status=422)
    events = lab.recognition_events()
    kinds = [event["type"] for event in events]
    assert kinds.count("recognition_capture_failed") == 4
    assert "recognition_ambiguous" in kinds
    # Mesmo fora do bloco autorizado, a decisão fica com a autoria do operador.
    assert {event["actor"] for event in events} == {ADMIN["username"]}


def test_cancelled_and_expired_attempts_are_denied_and_logged(lab):
    lab.create_identity()
    lab.self_enroll()
    challenge = lab.operator.post("/api/recognition/challenge", json={}).json()
    cancel = lab.operator.request("DELETE",
                                  f"/api/recognition/challenge/{challenge['challenge_id']}",
                                  headers=JSON)
    assert cancel.status_code == 200
    body = {"challenge_id": challenge["challenge_id"], "front": b64("PESSOA:titular:1:0.0"),
            "turned": [b64("PESSOA:titular:2:0.3"), b64("PESSOA:titular:3:-0.3")]}
    _assert_denied(lab, lab.operator.post("/api/recognition/verify", json=body),
                   "challenge_expired")

    challenge = lab.operator.post("/api/recognition/challenge", json={}).json()
    lab.wall[0] += 46
    body["challenge_id"] = challenge["challenge_id"]
    _assert_denied(lab, lab.operator.post("/api/recognition/verify", json=body),
                   "challenge_expired")
    kinds = [event["type"] for event in lab.recognition_events()]
    assert kinds.count("recognition_cancelled") == 1
    assert kinds.count("recognition_expired") == 1  # o cancelado não gera evento duplicado


def test_missing_models_or_failing_engine_fail_closed(lab):
    lab.create_identity()
    lab.self_enroll()
    lab.app.state.recognition.engine = UnavailableEngine("Modelos ausentes (teste).")
    reply = lab.operator.post("/api/recognition/challenge", json={})
    assert reply.status_code == 503 and reply.json()["decision"]["granted"] is False
    assert lab.door()["secured"]

    class ExplodingEngine(FakeFaceEngine):
        def read(self, image):
            raise RuntimeError("falha interna simulada do OpenCV")

    lab.app.state.recognition.engine = ExplodingEngine()
    _assert_denied(lab, lab.access_point(), "engine_error", status=503)

    class VanishingEngine(FakeFaceEngine):
        def read(self, image):
            from everlock.faces import FaceError
            raise FaceError("engine_unavailable", "Modelos removidos durante a análise.")

    lab.app.state.recognition.engine = VanishingEngine()
    reply = lab.access_point()
    assert reply.status_code == 503 and lab.door()["secured"]
    kinds = [event["type"] for event in lab.recognition_events()]
    assert kinds.count("recognition_unavailable") == 2 and "recognition_error" in kinds


def test_door_rules_still_apply_after_an_authorized_recognition(lab):
    lab.create_identity()
    lab.self_enroll()
    assert lab.operator.post("/api/actions", json={"action": "exit"}).status_code == 200
    refused = lab.access_point()
    assert refused.status_code == 409 and refused.json()["code"] == "door_open"
    assert refused.json()["decision"]["granted"] is False
    event = lab.recognition_events()[0]
    assert event["type"] == "recognition_denied" and event["outcome"] == "denied"


# --- 3. o servidor decide; a interface não basta ------------------------------------------


def test_backend_enforces_roles_for_access_point_and_actuation(lab):
    lab.create_identity()
    lab.self_enroll()
    # Uma conta comum não opera o ponto de acesso nem libera a trava pela API.
    assert lab.person.post("/api/recognition/challenge", json={}).status_code == 403
    assert lab.person.post("/api/recognition/verify", json={
        "challenge_id": "x" * 20, "front": b64("PESSOA:titular:1"),
        "turned": [b64("PESSOA:titular:2:0.3")]}).status_code == 403
    assert lab.person.post("/api/actions", json={"action": "unlock"}).status_code == 403
    # Nem vincula a si mesma a uma identidade ou altera horários.
    assert lab.person.put("/api/identities/1/account",
                          json={"account_id": lab.person_id}).status_code == 403
    assert lab.person.patch("/api/identities/1", json={"active": True}).status_code == 403
    anonymous = TestClient(lab.app, base_url="http://localhost")
    assert anonymous.get("/api/me/door-access").status_code == 401
    assert lab.door()["secured"]


def test_self_service_requires_link_consent_and_password(lab):
    unlinked = lab.person.get("/api/me/door-access").json()
    assert unlinked == {"linked": False, "identity": None,
                        "policy": unlinked["policy"], "engine": unlinked["engine"]}
    assert unlinked["policy"]["version"] == CONSENT_VERSION
    assert lab.person.post("/api/me/door-access/consent", json={
        "accepted": True, "version": CONSENT_VERSION}).status_code == 404

    identity = lab.create_identity()
    photos = [b64(f"PESSOA:titular:{n}") for n in range(5)]
    no_consent = lab.person.post("/api/me/door-access/face",
                                 json={"password": PERSON["password"], "images": photos})
    assert no_consent.status_code == 409
    assert lab.person.post("/api/me/door-access/consent", json={
        "accepted": False, "version": CONSENT_VERSION}).status_code == 422
    assert lab.person.post("/api/me/door-access/consent", json={
        "accepted": True, "version": "1999-01-01"}).status_code == 409
    assert lab.person.post("/api/me/door-access/consent", json={
        "accepted": True, "version": CONSENT_VERSION}).status_code == 200
    wrong = lab.person.post("/api/me/door-access/face",
                            json={"password": "Errada1!", "images": photos})
    assert wrong.status_code == 403
    assert lab.person.get("/api/me/door-access").json()["identity"]["face_samples"] == 0
    assert lab.self_enroll()["access"]["identity"]["face_samples"] == 5

    audit = lab.operator.get("/api/identities/events").json()["items"]
    kinds = [item["type"] for item in audit]
    assert "subject_consent_self" in kinds and "face_enrolled" in kinds
    assert all("Titular 01" not in item["detail"] for item in audit)
    listed = lab.operator.get("/api/identities").json()["items"][0]
    assert listed["account"] == {"id": lab.person_id, "username": "titular", "active": True}
    assert listed["consent"]["subject_method"] == "own_account"

    removed = lab.person.request("DELETE", "/api/me/door-access/face", headers=JSON)
    assert removed.status_code == 200
    assert removed.json()["access"]["identity"]["face_samples"] == 0
    _assert_denied(lab, lab.access_point(), "no_faces_enrolled")
    assert identity["id"] == listed["id"]


def test_linking_rules(lab):
    first = lab.create_identity()
    second = lab.operator.post("/api/identities", json={
        "label": "Segunda", "consent": True, "consent_version": CONSENT_VERSION,
        "account_id": lab.person_id})
    assert second.status_code == 409  # uma identidade por conta
    assert lab.operator.post("/api/identities", json={
        "label": "Fantasma", "consent": True, "consent_version": CONSENT_VERSION,
        "account_id": 9999}).status_code == 404
    names = [item["label"] for item in lab.operator.get("/api/identities").json()["items"]]
    assert names == ["Titular 01"]  # recusas não deixam identidade pela metade
    unlink = lab.operator.put(f"/api/identities/{first['id']}/account", json={"account_id": None})
    assert unlink.status_code == 200 and unlink.json()["account"] is None
    assert lab.person.get("/api/me/door-access").json()["linked"] is False
    relink = lab.operator.put(f"/api/identities/{first['id']}/account",
                              json={"account_id": lab.person_id})
    assert relink.status_code == 200 and relink.json()["account"]["username"] == "titular"


# --- 4. privacidade do histórico ---------------------------------------------------------


def test_history_records_decisions_without_images_vectors_or_labels(lab):
    identity = lab.create_identity()
    lab.self_enroll()
    lab.access_point()
    lab.access_point("desconhecido")
    lab.access_point(front="BORRADO")
    texts = lab.operator.get("/api/events?limit=100").text
    csv_text = lab.operator.get("/api/events/export.csv").text
    sealed = lab.app.state.identities.db.execute("SELECT sealed FROM face_templates").fetchall()
    assert sealed
    for blob in (texts, csv_text):
        assert "Titular 01" not in blob and "PESSOA:" not in blob and "base64" not in blob
        assert f"#{identity['id']}" in blob
        for row in sealed:
            assert base64.b64encode(row["sealed"]).decode()[:24] not in blob
            assert row["sealed"].hex()[:24] not in blob
    columns = {row[1] for table in ("events", "identities", "face_templates")
               for row in lab.app.state.identities.db.execute(f"PRAGMA table_info({table})")}
    assert not {"image", "photo", "foto", "imagem", "frame"} & columns


# --- 5. uso normal usa o pipeline OpenCV local, não um dublê ------------------------------


def test_normal_application_wires_the_real_opencv_pipeline(tmp_path, monkeypatch):
    monkeypatch.setenv("EVERLOCK_DATA_DIR", str(tmp_path / "dados"))
    app = create_app()  # exatamente como o servidor (uvicorn factory) cria a aplicação
    with TestClient(app, base_url="http://localhost") as client:
        recognition, face_login = app.state.recognition, app.state.face_login
        assert type(recognition.engine) is OpenCVFaceEngine
        assert face_login.engine is recognition.engine
        assert recognition.engine.models_dir == (tmp_path / "dados" / "models").resolve()
        assert client.post("/api/auth/setup", json=ADMIN).status_code == 201
        Lab.login(client, ADMIN)
        status = client.get("/api/faces/status").json()
        assert status["engine_kind"] == "opencv" and status["test_double"] is False
        # Sem modelos nesta pasta temporária: a porta falha fechada e registra a decisão.
        assert status["available"] is False
        reply = client.post("/api/recognition/challenge", json={})
        assert reply.status_code == 503 and reply.json()["decision"]["granted"] is False
        assert client.get("/api/status").json()["door"]["secured"] is True
        assert client.get("/api/events?type=recognition_unavailable").json()["items"]


def test_application_package_contains_no_test_double_or_canned_match():
    package = Path(everlock.__file__).parent
    sources = {path.name: path.read_text(encoding="utf-8") for path in package.glob("*.py")}
    for name, text in sources.items():
        assert "FakeFaceEngine" not in text and "from fakes" not in text, name
        assert not re.search(r"^\s*(from|import)\s+(fakes|tests)", text, re.MULTILINE), name
    # O único "resultado preparado" do produto é o teste simulado, isolado em sua rota e
    # sempre marcado como simulado; o ponto de acesso real chama apenas /recognition/verify.
    script = (package / "web" / "faces.js").read_text(encoding="utf-8")
    assert "recognition/verify" in script and "recognition/simulate" not in script


MODELS_DIR = os.getenv("EVERLOCK_TEST_MODELS_DIR")


@pytest.mark.skipif(not MODELS_DIR, reason="defina EVERLOCK_TEST_MODELS_DIR com os modelos "
                                           "YuNet/SFace para exercitar o OpenCV real")
def test_real_opencv_pipeline_rejects_synthetic_non_face_frames(tmp_path):
    """Quadros gerados por código (sem pessoas) passam pelo YuNet/SFace reais e são recusados."""
    import cv2
    import numpy

    engine = OpenCVFaceEngine(Path(MODELS_DIR))
    assert engine.available, engine.reason
    frames = []
    for seed in range(3):
        noise = numpy.random.default_rng(seed).integers(0, 256, (480, 640, 3), dtype=numpy.uint8)
        frames.append(noise)
    frames.append(numpy.full((480, 640, 3), 128, dtype=numpy.uint8))
    images = [cv2.imencode(".jpg", frame)[1].tobytes() for frame in frames]
    with Lab(tmp_path, engine=engine) as lab:
        assert lab.operator.get("/api/faces/status").json()["engine_kind"] == "opencv"
        for image in images:
            challenge = lab.operator.post("/api/recognition/challenge", json={}).json()
            encoded = base64.b64encode(image).decode()
            reply = lab.operator.post("/api/recognition/verify", json={
                "challenge_id": challenge["challenge_id"], "front": encoded,
                "turned": [encoded]})
            assert reply.status_code == 422 and reply.json()["code"] == "no_face"
            assert reply.json()["decision"]["granted"] is False
            assert lab.door()["secured"] is True
        kinds = [event["type"] for event in lab.recognition_events()]
        assert kinds.count("recognition_capture_failed") == len(images)
