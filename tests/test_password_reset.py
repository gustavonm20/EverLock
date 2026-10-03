import pytest
from fakes import RecordingMailer
from fastapi.testclient import TestClient

from everlock.accounts import RESET_REQUEST_LIMIT, RESET_SECONDS
from everlock.app import create_app
from everlock.mailer import Mailer

ADMIN = {"username": "admin", "email": "admin@example.com", "password": "Senha de testes1!"}
MARIA = {"username": "maria", "email": "maria@example.com", "password": "Ab1@cd"}
NEW = "Nova#senha9"


@pytest.fixture
def lab(tmp_path):
    clock, mailer = [7000.0], RecordingMailer()
    app = create_app(tmp_path / "reset.sqlite3", session_clock=lambda: clock[0], mailer=mailer)
    with TestClient(app, base_url="http://localhost") as admin:
        assert admin.post("/api/auth/setup", json=ADMIN).status_code == 201
        admin.post("/api/auth/login", json={"identifier": "admin", "password": ADMIN["password"]})
        assert admin.post("/api/auth/users", json={**MARIA, "role": "user"}).status_code == 201
        anonymous = TestClient(app, base_url="http://localhost")
        yield admin, anonymous, mailer, clock, app


def forgot(client, identifier):
    return client.post("/api/auth/forgot-password", json={"identifier": identifier})


def reset(client, token, password=NEW, confirm=None):
    return client.post("/api/auth/reset-password", json={
        "token": token, "password": password, "confirm_password": confirm or password})


def login(client, identifier, password):
    return client.post("/api/auth/login", json={"identifier": identifier, "password": password})


def test_response_is_the_same_for_existing_and_unknown_accounts(lab):
    _, anonymous, mailer, _, _ = lab
    known, unknown = forgot(anonymous, "maria@example.com"), forgot(anonymous, "ninguem@x.com")
    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json() and "1 hora" in known.json()["message"]
    assert len(mailer.resets) == 1 and mailer.resets[0]["to"] == "maria@example.com"
    assert "token" not in known.text and mailer.resets[0]["token"] not in known.text
    for variant in ("MARIA", " Maria@Example.COM "):  # usuário e e-mail, sem diferenciar caixa
        assert forgot(anonymous, variant).status_code == 202
    assert len(mailer.resets) == 3


def test_reset_changes_the_password_once_and_revokes_sessions(lab):
    admin, anonymous, mailer, _, app = lab
    maria = TestClient(app, base_url="http://localhost")
    assert login(maria, "maria", MARIA["password"]).status_code == 200
    assert maria.get("/api/status").status_code == 200
    forgot(anonymous, "maria")
    token = mailer.resets[-1]["token"]
    assert reset(anonymous, token).status_code == 200
    assert maria.get("/api/status").status_code == 401  # sessão antiga encerrada
    assert login(anonymous, "maria", MARIA["password"]).status_code == 401
    assert login(anonymous, "maria@example.com", NEW).status_code == 200
    assert reset(anonymous, token).status_code == 400  # uso único
    events = admin.get("/api/auth/events").text
    assert "password_reset_requested" in events and "password_reset" in events
    assert token not in events and NEW not in events


def test_reset_clears_a_login_lockout(lab):
    _, anonymous, mailer, _, _ = lab
    for _ in range(5):
        assert login(anonymous, "maria", "errada").status_code == 401
    assert login(anonymous, "maria", MARIA["password"]).status_code == 429  # bloqueada
    forgot(anonymous, "maria")
    assert reset(anonymous, mailer.resets[-1]["token"]).status_code == 200
    assert login(anonymous, "maria", NEW).status_code == 200


def test_token_expires_and_a_new_request_replaces_the_old_link(lab):
    _, anonymous, mailer, clock, _ = lab
    forgot(anonymous, "maria")
    old = mailer.resets[-1]["token"]
    forgot(anonymous, "maria")
    fresh = mailer.resets[-1]["token"]
    assert old != fresh and reset(anonymous, old).status_code == 400
    clock[0] += RESET_SECONDS + 1
    assert reset(anonymous, fresh).status_code == 400
    assert login(anonymous, "maria", MARIA["password"]).status_code == 200  # nada mudou


def test_invalid_input_is_refused_without_changing_anything(lab):
    _, anonymous, mailer, _, _ = lab
    forgot(anonymous, "maria")
    token = mailer.resets[-1]["token"]
    assert reset(anonymous, token, "fraca").status_code == 422  # política de senha
    assert reset(anonymous, token, NEW, "Outra#senha9").status_code == 422  # confirmação
    assert reset(anonymous, "x" * 43).status_code == 400  # token inexistente
    for body in ({"token": "curto", "password": NEW, "confirm_password": NEW},
                 {"token": token, "password": NEW, "confirm_password": NEW, "x": 1},
                 {"token": token}):
        assert anonymous.post("/api/auth/reset-password", json=body).status_code == 422
    for body in ({"identifier": "ab"}, {}, {"identifier": "maria", "x": 1}):
        assert anonymous.post("/api/auth/forgot-password", json=body).status_code == 422
    assert reset(anonymous, token).status_code == 200  # o link continuava valendo


def test_only_active_confirmed_accounts_receive_a_link(lab):
    admin, anonymous, mailer, _, _ = lab
    users = {u["username"]: u for u in admin.get("/api/auth/users").json()["items"]}
    assert admin.patch(f"/api/auth/users/{users['maria']['id']}",
                       json={"role": "user", "active": False}).status_code == 200
    assert forgot(anonymous, "maria").status_code == 202 and not mailer.resets
    admin.patch(f"/api/auth/users/{users['maria']['id']}", json={"role": "user", "active": True})
    anonymous.post("/api/auth/register", json={
        "username": "nova", "email": "nova@example.com", "password": "Ab1@cd",
        "confirm_password": "Ab1@cd"})
    assert forgot(anonymous, "nova").status_code == 202 and not mailer.resets  # sem confirmar
    assert forgot(anonymous, "admin").status_code == 202 and len(mailer.resets) == 1


def test_requests_are_rate_limited_per_client(lab):
    _, anonymous, mailer, clock, _ = lab
    for _ in range(RESET_REQUEST_LIMIT):
        assert forgot(anonymous, "ninguem@x.com").status_code == 202
    blocked = forgot(anonymous, "maria")
    assert blocked.status_code == 429 and not mailer.resets
    clock[0] += 301
    assert forgot(anonymous, "maria").status_code == 202 and len(mailer.resets) == 1


def test_mail_failure_does_not_reveal_anything(lab):
    admin, anonymous, mailer, _, _ = lab
    mailer.fail = True
    broken = forgot(anonymous, "maria")
    assert broken.status_code == 202 and broken.json() == forgot(anonymous, "ninguem@x.com").json()
    assert "password_reset_mail_failed" in admin.get("/api/auth/events").text


def test_cross_origin_requests_are_blocked(lab):
    _, anonymous, mailer, _, _ = lab
    hostile = anonymous.post("/api/auth/forgot-password", json={"identifier": "maria"},
                             headers={"Origin": "https://outro-site.example"})
    assert hostile.status_code == 403 and not mailer.resets


def test_without_email_settings_the_link_goes_to_the_terminal(tmp_path, capsys):
    app = create_app(tmp_path / "console.sqlite3", mailer=Mailer(None, "http://127.0.0.1:8000"))
    with TestClient(app, base_url="http://localhost") as client:
        assert client.post("/api/auth/setup", json=ADMIN).status_code == 201
        response = forgot(client, "admin")
    assert response.status_code == 202 and "terminal" in response.json()["message"]
    printed = capsys.readouterr().out
    assert "http://127.0.0.1:8000/#redefinir=" in printed and "#redefinir=" not in response.text
