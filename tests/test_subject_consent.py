import base64

import pytest
from fakes import FakeFaceEngine
from fastapi import HTTPException
from fastapi.testclient import TestClient

from everlock import identity_api
from everlock.app import create_app
from everlock.identities import CONSENT_VERSION, SECONDS_PER_DAY

EPOCH = 1_790_000_000.0
ADMIN = {"username": "admin", "email": "admin@example.com", "password": "Teste seguro1!"}
ACCEPT = {"accepted": True, "version": CONSENT_VERSION}


@pytest.fixture
def lab(tmp_path):
    real = [EPOCH]
    engine = FakeFaceEngine()
    app = create_app(tmp_path / "consent.sqlite3", clock=lambda: 0,
                     session_clock=lambda: real[0], face_engine=engine)
    with TestClient(app, base_url="http://localhost") as client:
        assert client.post("/api/auth/setup", json=ADMIN).status_code == 201
        assert client.post("/api/auth/login", json={
            "identifier": ADMIN["username"], "password": ADMIN["password"],
        }).status_code == 200
        created = client.post("/api/identities", json={
            "label": "Pessoa de teste", "consent": True, "consent_version": CONSENT_VERSION,
            "retention_days": 1,
        })
        assert created.status_code == 201
        yield client, app, real, engine, created.json()


def images():
    return [base64.b64encode(f"PESSOA:teste:{index}".encode()).decode() for index in range(3)]


def test_missing_subject_declaration_blocks_before_decoding_engine_or_storage(lab, monkeypatch):
    client, app, _, engine, identity = lab
    identity_id = identity["id"]

    def forbidden(*_args):
        pytest.fail("Não deve processar nem cifrar uma imagem sem a declaração do titular.")

    monkeypatch.setattr(identity_api, "decode_image", forbidden)
    monkeypatch.setattr(engine, "read", forbidden)
    monkeypatch.setattr(app.state.identities.vault, "seal", forbidden)
    response = client.post(f"/api/identities/{identity_id}/face", json={"images": images()})
    assert response.status_code == 409
    with pytest.raises(HTTPException) as service_error:
        app.state.recognition.enroll_face(identity_id, [b"not an image"] * 3, "admin")
    assert service_error.value.status_code == 409
    with pytest.raises(HTTPException) as storage_error:
        app.state.identities.enroll_face(identity_id, [[0.0] * 128] * 3, "falso", "admin")
    assert storage_error.value.status_code == 409
    assert app.state.identities.db.execute("SELECT count(*) FROM face_templates").fetchone()[0] == 0
    assert not app.state.identities.vault.key_path.exists()


@pytest.mark.parametrize(("accepted", "version", "expected"), [
    (False, CONSENT_VERSION, 422),
    ("true", CONSENT_VERSION, 422),
    (True, "termo-antigo", 409),
])
def test_false_or_stale_declaration_does_not_record_consent(lab, accepted, version, expected):
    client, app, _, _, identity = lab
    response = client.post(f"/api/identities/{identity['id']}/consent/confirm", json={
        "accepted": accepted, "version": version,
    })
    assert response.status_code == expected
    assert app.state.identities.list()[0]["consent"]["subject_confirmed_at"] is None
    recorded = {event["type"] for event in app.state.identities.events()}
    assert "subject_consent_declared" not in recorded


def test_declaration_neither_enrolls_nor_actuates_nor_extends_retention(lab):
    client, app, real, _, identity = lab
    path = f"/api/identities/{identity['id']}/consent/confirm"
    before = client.get("/api/status").json()["door"]
    real[0] += 120
    for _ in range(2):
        response = client.post(path, json=ACCEPT)
        assert response.status_code == 200
        current = response.json()
        assert current["consent"]["subject_confirmed_at"] == real[0]
        assert current["consent"]["subject_version"] == CONSENT_VERSION
        assert current["consent"]["granted_at"] == identity["consent"]["granted_at"]
        assert current["expires_at"] == identity["expires_at"]
        assert current["face_samples"] == 0 and current["enrollment"] == "none"
        assert current["access_now"]["allowed"] is False
        assert client.get("/api/status").json()["door"] == before
    assert not app.state.identities.vault.key_path.exists()


@pytest.mark.parametrize(("change", "expected"), [("revoked", 409), ("expired", 404),
                                                   ("old_identity_term", 409)])
def test_invalid_identity_cannot_confirm_or_enroll(lab, monkeypatch, change, expected):
    client, app, real, engine, identity = lab
    prefix = f"/api/identities/{identity['id']}"
    assert client.post(f"{prefix}/consent/confirm", json=ACCEPT).status_code == 200
    if change == "revoked":
        assert client.post(f"{prefix}/consent/revoke", json={}).status_code == 200
    elif change == "expired":
        real[0] += SECONDS_PER_DAY
        # Renova a sessão real; não confunde expiração da sessão com a retenção da identidade.
        assert client.post("/api/auth/login", json={
            "identifier": ADMIN["username"], "password": ADMIN["password"],
        }).status_code == 200
    else:
        with app.state.identities.db:
            app.state.identities.db.execute("UPDATE identities SET consent_version='antigo'")

    def forbidden(_image):
        pytest.fail("A identidade inválida não pode chegar ao motor facial.")

    monkeypatch.setattr(engine, "read", forbidden)
    assert client.post(f"{prefix}/consent/confirm", json=ACCEPT).status_code == expected
    assert client.post(f"{prefix}/face", json={"images": images()}).status_code == expected
    assert app.state.identities.db.execute("SELECT count(*) FROM face_templates").fetchone()[0] == 0


def test_anonymous_and_nonadmin_cannot_record_subject_declaration(lab):
    client, app, _, _, identity = lab
    path = f"/api/identities/{identity['id']}/consent/confirm"
    user = {"username": "usuario", "email": "usuario@example.com", "password": "Senha segura1!"}
    assert client.post("/api/auth/users", json={**user, "role": "user"}).status_code == 201
    anonymous = TestClient(app, base_url="http://localhost")
    try:
        assert anonymous.post(path, json=ACCEPT).status_code == 401
        assert anonymous.post("/api/auth/login", json={
            "identifier": user["username"], "password": user["password"],
        }).status_code == 200
        assert anonymous.post(path, json=ACCEPT).status_code == 403
        assert app.state.identities.list()[0]["consent"]["subject_confirmed_at"] is None
    finally:
        anonymous.close()


def test_expiry_during_engine_processing_is_rechecked_before_storage(lab, monkeypatch):
    client, app, real, engine, identity = lab
    prefix = f"/api/identities/{identity['id']}"
    assert client.post(f"{prefix}/consent/confirm", json=ACCEPT).status_code == 200
    read = engine.read

    def expire_while_reading(image):
        result = read(image)
        real[0] = EPOCH + SECONDS_PER_DAY
        return result

    monkeypatch.setattr(engine, "read", expire_while_reading)
    assert client.post(f"{prefix}/face", json={"images": images()}).status_code == 404
    assert app.state.identities.db.execute("SELECT count(*) FROM face_templates").fetchone()[0] == 0
    assert not app.state.identities.vault.key_path.exists()
