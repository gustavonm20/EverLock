import base64

import pytest
from fakes import FakeFaceEngine
from fastapi.testclient import TestClient

from everlock.app import create_app
from everlock.biometrics import TemplateVault
from everlock.face_login import CONSENT_VERSION
from everlock.faces import UnavailableEngine

EPOCH = 1_790_000_000.0
ADMIN = {"username": "admin", "email": "admin@example.com", "password": "Senha de testes1!"}
MARIA = {"username": "maria", "email": "maria@example.com", "password": "Ab1@cd"}
JSON = {"Content-Type": "application/json"}


def b64(text):
    return base64.b64encode(text.encode()).decode()


def photos(name, count=5):
    return [b64(f"PESSOA:{name}:{n}") for n in range(count)]


def sign_in(client, username, password):
    credentials = {"identifier": username, "password": password}
    assert client.post("/api/auth/login", json=credentials).status_code == 200


@pytest.fixture
def lab(tmp_path):
    wall = [EPOCH]
    app = create_app(tmp_path / "login.sqlite3", clock=lambda: 0, session_clock=lambda: wall[0],
                     face_engine=FakeFaceEngine())
    with TestClient(app, base_url="http://localhost") as admin:
        assert admin.post("/api/auth/setup", json=ADMIN).status_code == 201
        sign_in(admin, "admin", ADMIN["password"])
        assert admin.post("/api/auth/users", json={**MARIA, "role": "user"}).status_code == 201
        maria = TestClient(app, base_url="http://localhost")
        sign_in(maria, "maria", MARIA["password"])
        anonymous = TestClient(app, base_url="http://localhost")
        yield admin, maria, anonymous, wall, app


def enroll(client, password, person, **extra):
    body = {"password": password, "consent": True, "images": photos(person), **extra}
    return client.post("/api/auth/face/enroll", json=body)


def face_login(anonymous, person, *, front_yaw=0.0, turn=None, turned_person=None, frames=3,
               challenge=None):
    """Faz o desafio e a entrada. `turn` = giro enviado (padrão: o giro certo do desafio)."""
    challenge = challenge or anonymous.post("/api/auth/face/challenge", json={}).json()
    sign = 1 if challenge["direction"] == "left" else -1
    yaw = sign * 0.30 if turn is None else turn
    who = turned_person or person
    body = {"challenge_id": challenge["challenge_id"],
            "front": b64(f"PESSOA:{person}:front:{front_yaw}"),
            "turned": [b64(f"PESSOA:{who}:t{n}:{yaw}") for n in range(frames)]}
    return anonymous.post("/api/auth/face/login", json=body)


def audit(client):
    return client.get("/api/auth/events").text


# --- disponibilidade e permissões ------------------------------------------------------------


def test_availability_is_public_but_the_rest_needs_a_session(lab):
    admin, maria, anonymous, _, _ = lab
    assert anonymous.get("/api/auth/face/availability").json() == {"available": True, "reason": ""}
    assert anonymous.get("/api/auth/face/me").status_code == 401
    assert anonymous.post("/api/auth/face/enroll", json={"password": "x", "consent": True,
                                                         "images": photos("a")}).status_code == 401
    assert anonymous.delete("/api/auth/face", headers=JSON).status_code == 401
    assert anonymous.delete("/api/auth/users/1/face", headers=JSON).status_code == 401
    info = maria.get("/api/auth/face/me").json()
    assert info["enrolled"] is False and info["consent"]["version"] == CONSENT_VERSION
    nothing = face_login(anonymous, "ana")  # ninguém cadastrou rosto ainda
    assert nothing.status_code == 409 and nothing.json()["code"] == "no_faces_enrolled"
    assert "cadastre seu rosto" in nothing.json()["message"]


def test_engine_unavailable_disables_face_login_safely(tmp_path):
    app = create_app(tmp_path / "off.sqlite3", face_engine=UnavailableEngine("sem modelos"))
    with TestClient(app, base_url="http://localhost") as client:
        assert client.post("/api/auth/setup", json=ADMIN).status_code == 201
        assert client.get("/api/auth/face/availability").json() == {
            "available": False, "reason": "sem modelos"}
        sign_in(client, "admin", ADMIN["password"])
        assert enroll(client, ADMIN["password"], "ana").status_code == 503
        assert face_login(client, "ana").status_code == 503


# --- cadastro do rosto da conta -----------------------------------------------------------------


def test_enrollment_needs_password_consent_and_good_samples(lab):
    _, maria, _, _, app = lab
    wrong = enroll(maria, "senha errada", "maria")
    assert wrong.status_code == 403 and wrong.json()["detail"] == "Senha incorreta."
    for extra in ({"consent": False}, {"images": photos("m", 2)}, {"images": photos("m", 6)},
                  {"extra": 1}):
        assert enroll(maria, MARIA["password"], "m", **extra).status_code == 422, extra
    mixed = [b64("PESSOA:maria:1"), b64("PESSOA:maria:2"), b64("PESSOA:outra:1")]
    inconsistent = maria.post("/api/auth/face/enroll", json={
        "password": MARIA["password"], "consent": True, "images": mixed})
    assert inconsistent.status_code == 422 and inconsistent.json()["code"] == "inconsistent_samples"
    assert maria.get("/api/auth/face/me").json()["enrolled"] is False

    done = enroll(maria, MARIA["password"], "maria")
    assert done.status_code == 201 and done.json()["face"]["samples"] == 5
    info = maria.get("/api/auth/face/me").json()
    assert info["enrolled"] and info["samples"] == 5 and info["consent_version"] == CONSENT_VERSION
    rows = app.state.accounts.db.execute("SELECT sealed FROM account_faces").fetchall()
    assert len(rows) == 5 and all(len(row["sealed"]) == 12 + 512 + 16 for row in rows)
    assert "face_enrolled" in audit(lab[0])
    assert enroll(maria, MARIA["password"], "maria").status_code == 201  # refazer substitui
    assert app.state.accounts.db.execute("SELECT COUNT(*) FROM account_faces").fetchone()[0] == 5


def test_one_face_cannot_belong_to_two_accounts(lab):
    admin, maria, _, _, _ = lab
    assert enroll(admin, ADMIN["password"], "ana").status_code == 201
    duplicate = enroll(maria, MARIA["password"], "ana")
    assert duplicate.status_code == 409 and duplicate.json()["code"] == "face_already_enrolled"
    assert maria.get("/api/auth/face/me").json()["enrolled"] is False


def test_vault_scopes_keep_account_and_door_vectors_apart(tmp_path):
    vault = TemplateVault(tmp_path / "chave.bin")
    vector = FakeFaceEngine._unit("a")
    sealed = vault.seal(1, vector, "conta")
    assert vault.open(1, sealed, "conta") == pytest.approx(vector, abs=1e-6)
    with pytest.raises(ValueError):
        vault.open(1, sealed)  # escopo "identidade"
    with pytest.raises(ValueError):
        vault.open(2, sealed, "conta")


# --- entrar pelo rosto --------------------------------------------------------------------------


def test_registered_face_with_the_asked_movement_starts_a_session(lab):
    admin, maria, anonymous, _, _ = lab
    assert enroll(admin, ADMIN["password"], "ana").status_code == 201
    assert enroll(maria, MARIA["password"], "bia").status_code == 201
    challenge = anonymous.post("/api/auth/face/challenge", json={}).json()
    assert challenge["direction"] in {"left", "right"} and "sua" in challenge["instruction"]
    assert anonymous.get("/api/auth/session").json()["user"] is None
    response = face_login(anonymous, "bia", challenge=challenge)
    assert response.status_code == 200 and "reconhecido" in response.json()["message"]
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert anonymous.get("/api/auth/session").json()["user"]["username"] == "maria"
    assert anonymous.get("/api/status").status_code == 200
    assert "login_face" in audit(admin) and "(" not in audit(admin).split("login_face")[1][:5]
    # O desafio vale uma vez só: repetir os mesmos dados é recusado.
    again = face_login(anonymous, "bia", challenge=challenge)
    assert again.status_code == 409 and again.json()["code"] == "challenge_expired"


def test_face_not_in_the_database_says_face_not_registered(lab):
    admin, _, anonymous, _, _ = lab
    assert enroll(admin, ADMIN["password"], "ana").status_code == 201
    response = face_login(anonymous, "carlos")
    assert response.status_code == 409 and response.json()["code"] == "no_match"
    assert "Face não cadastrada" in response.json()["message"]
    assert "set-cookie" not in response.headers
    assert anonymous.get("/api/auth/session").json()["user"] is None
    assert "login_face_denied" in audit(admin) and "carlos" not in audit(admin)


def test_photo_without_the_requested_movement_is_refused(lab):
    admin, _, anonymous, _, _ = lab
    assert enroll(admin, ADMIN["password"], "ana").status_code == 201
    still = face_login(anonymous, "ana", turn=0.0)  # foto parada: sem giro
    assert still.status_code == 409 and still.json()["code"] == "liveness_failed"
    challenge = anonymous.post("/api/auth/face/challenge", json={}).json()
    opposite = -0.30 if challenge["direction"] == "left" else 0.30
    wrong_way = face_login(anonymous, "ana", turn=opposite, challenge=challenge)
    assert wrong_way.json()["code"] == "liveness_failed"
    crooked = face_login(anonymous, "ana", front_yaw=0.40)  # já começou virado
    assert crooked.json()["code"] == "liveness_failed"
    small = face_login(anonymous, "ana", turn=0.05)  # giro pequeno demais, nos dois sentidos
    assert small.json()["code"] == "liveness_failed"
    assert anonymous.get("/api/auth/session").json()["user"] is None


def test_a_different_face_in_the_turned_photos_is_refused(lab):
    admin, _, anonymous, _, _ = lab
    assert enroll(admin, ADMIN["password"], "ana").status_code == 201
    swapped = face_login(anonymous, "ana", turned_person="carlos")
    assert swapped.status_code == 409 and swapped.json()["code"] == "face_changed"
    assert anonymous.get("/api/auth/session").json()["user"] is None


@pytest.mark.parametrize("change", ["expires", "session_expires", "cancelled", "removed",
                                   "deactivated"])
def test_pending_face_login_cannot_outlive_challenge_or_account_face(lab, monkeypatch, change):
    admin, maria, anonymous, wall, app = lab
    assert enroll(maria, MARIA["password"], "bia").status_code == 201
    challenge = anonymous.post("/api/auth/face/challenge", json={}).json()
    original_read, changed = app.state.face_login.engine.read, False

    def read(image):
        nonlocal changed
        reading = original_read(image)
        if not changed:
            changed = True
            if change == "expires":
                wall[0] += 46
            elif change == "cancelled":
                path = f"/api/auth/face/challenge/{challenge['challenge_id']}"
                assert anonymous.delete(path, headers=JSON).status_code == 200
            elif change == "removed":
                assert maria.delete("/api/auth/face", headers=JSON).status_code == 200
            elif change == "deactivated":
                user_id = maria.get("/api/auth/session").json()["user"]["id"]
                assert admin.patch(f"/api/auth/users/{user_id}",
                                   json={"role": "user", "active": False}).status_code == 200
        return reading

    monkeypatch.setattr(app.state.face_login.engine, "read", read)
    if change == "session_expires":
        original_login = app.state.accounts.login_by_face

        def create_session(user_id):
            token = original_login(user_id)
            wall[0] += 46
            return token

        monkeypatch.setattr(app.state.accounts, "login_by_face", create_session)
    response = face_login(anonymous, "bia", challenge=challenge)
    assert response.status_code == 409 and "set-cookie" not in response.headers
    assert response.json()["code"] in {"challenge_expired", "no_faces_enrolled"}
    assert anonymous.get("/api/auth/session").json()["user"] is None


def test_face_login_rejects_replay_during_processing_and_a_partially_swapped_face(lab,
                                                                                monkeypatch):
    _, maria, anonymous, _, app = lab
    assert enroll(maria, MARIA["password"], "bia").status_code == 201
    challenge = anonymous.post("/api/auth/face/challenge", json={}).json()
    original_read, replayed = app.state.face_login.engine.read, False

    def read(image):
        nonlocal replayed
        if not replayed:
            replayed = True
            replay = face_login(anonymous, "bia", challenge=challenge)
            assert replay.status_code == 409 and replay.json()["code"] == "challenge_expired"
        return original_read(image)

    monkeypatch.setattr(app.state.face_login.engine, "read", read)
    yaw = 0.30 if challenge["direction"] == "left" else -0.30
    response = anonymous.post("/api/auth/face/login", json={
        "challenge_id": challenge["challenge_id"], "front": b64("PESSOA:bia:front:0"),
        "turned": [b64(f"PESSOA:{person}:turn:{yaw}") for person in ("bia", "carlos", "bia")],
    })
    assert response.status_code == 409 and response.json()["code"] == "face_changed"
    assert anonymous.get("/api/auth/session").json()["user"] is None


def test_account_face_enrollment_revalidates_session_after_processing(lab, monkeypatch):
    _, maria, _, _, app = lab
    original_read, logged_out = app.state.face_login.engine.read, False

    def read(image):
        nonlocal logged_out
        reading = original_read(image)
        if not logged_out:
            logged_out = True
            assert maria.post("/api/auth/logout", headers=JSON).status_code == 200
        return reading

    monkeypatch.setattr(app.state.face_login.engine, "read", read)
    assert enroll(maria, MARIA["password"], "bia").status_code == 401
    assert app.state.accounts.db.execute("SELECT COUNT(*) FROM account_faces").fetchone()[0] == 0


def test_capture_problems_and_bad_challenges(lab):
    admin, _, anonymous, wall, _ = lab
    assert enroll(admin, ADMIN["password"], "ana").status_code == 201
    challenge = anonymous.post("/api/auth/face/challenge", json={}).json()
    no_face = anonymous.post("/api/auth/face/login", json={
        "challenge_id": challenge["challenge_id"], "front": b64("SEMROSTO"),
        "turned": [b64("SEMROSTO")]})
    assert no_face.status_code == 422 and no_face.json()["code"] == "no_face"
    bogus = face_login(anonymous, "ana", challenge={"challenge_id": "x" * 20, "direction": "left"})
    assert bogus.status_code == 409 and bogus.json()["code"] == "challenge_expired"
    stale = anonymous.post("/api/auth/face/challenge", json={}).json()
    wall[0] += 46
    expired = face_login(anonymous, "ana", challenge=stale)
    assert expired.status_code == 409 and expired.json()["code"] == "challenge_expired"
    invalid = [{"challenge_id": "curto", "front": b64("x"), "turned": [b64("x")]},
               {"challenge_id": "x" * 20, "front": b64("x"), "turned": []},
               {"challenge_id": "x" * 20, "front": b64("x"), "turned": [b64("x")] * 7},
               {"challenge_id": "x" * 20, "front": "@@@", "turned": [b64("x")]},
               {"challenge_id": "x" * 20, "front": b64("x"), "turned": [b64("x")], "extra": 1}]
    for body in invalid:
        assert anonymous.post("/api/auth/face/login", json=body).status_code == 422, body


def test_repeated_failures_lock_face_login_for_everyone(lab):
    admin, _, anonymous, wall, _ = lab
    assert enroll(admin, ADMIN["password"], "ana").status_code == 201
    for number in range(5):
        assert face_login(anonymous, f"intruso{number}").json()["code"] == "no_match"
    blocked = face_login(anonymous, "ana")  # até o rosto certo espera
    assert blocked.status_code == 429 and blocked.json()["code"] == "rate_limited"
    assert anonymous.get("/api/auth/session").json()["user"] is None
    wall[0] += 121
    assert face_login(anonymous, "ana").status_code == 200


def test_similar_faces_are_refused_as_ambiguous(lab):
    admin, maria, anonymous, _, _ = lab
    assert enroll(admin, ADMIN["password"], "ana").status_code == 201
    assert enroll(maria, MARIA["password"], "bia").status_code == 201
    challenge = anonymous.post("/api/auth/face/challenge", json={}).json()
    sign = 1 if challenge["direction"] == "left" else -1
    response = anonymous.post("/api/auth/face/login", json={
        "challenge_id": challenge["challenge_id"],
        "front": b64("MISTURA:ana:bia:1"), "turned": [b64(f"PESSOA:ana:1:{sign * 0.3}")]})
    assert response.status_code == 409 and response.json()["code"] == "ambiguous"


def test_removed_deactivated_and_foreign_faces(lab):
    admin, maria, anonymous, _, _ = lab
    assert enroll(admin, ADMIN["password"], "ana").status_code == 201
    assert enroll(maria, MARIA["password"], "bia").status_code == 201
    users = {u["username"]: u for u in admin.get("/api/auth/users").json()["items"]}
    assert users["maria"]["face_samples"] == 5 and users["admin"]["face_samples"] == 5
    assert maria.delete(f"/api/auth/users/{users['admin']['id']}/face", headers=JSON
                        ).status_code == 403  # usuário não remove o rosto de outra conta
    # Conta desativada não entra pelo rosto.
    assert admin.patch(f"/api/auth/users/{users['maria']['id']}",
                       json={"role": "user", "active": False}).status_code == 200
    denied = face_login(anonymous, "bia")
    assert denied.status_code == 409 and denied.json()["code"] == "no_match"
    assert admin.patch(f"/api/auth/users/{users['maria']['id']}",
                       json={"role": "user", "active": True}).status_code == 200
    assert face_login(anonymous, "bia").status_code == 200
    # A própria pessoa remove o rosto e passa a entrar só com senha.
    assert maria.get("/api/auth/session").json()["user"] is None  # login novo troca a sessão
    sign_in(maria, "maria", MARIA["password"])
    assert maria.delete("/api/auth/face", headers=JSON).status_code == 200
    assert maria.delete("/api/auth/face", headers=JSON).status_code == 409
    again = face_login(TestClient(lab[4], base_url="http://localhost"), "bia")
    assert again.json()["code"] == "no_match"
    # O administrador remove o rosto de outra conta.
    assert admin.delete(f"/api/auth/users/{users['admin']['id']}/face", headers=JSON
                        ).status_code == 200
    assert admin.delete("/api/auth/users/999/face", headers=JSON).status_code == 404
