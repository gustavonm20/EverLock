import pytest
from fakes import RecordingMailer
from fastapi.testclient import TestClient

from everlock.accounts import INVITE_SECONDS, MAX_OPEN_INVITES
from everlock.app import create_app

ADMIN = {"username": "admin", "email": "admin@example.com", "password": "Senha de testes1!"}
NEWCOMER = {"username": "nova", "email": "nova@example.com", "password": "Ab1@cd",
            "confirm_password": "Ab1@cd"}


@pytest.fixture
def lab(tmp_path):
    clock, mailer = [9000.0], RecordingMailer()
    app = create_app(tmp_path / "invites.sqlite3", session_clock=lambda: clock[0], mailer=mailer)
    with TestClient(app, base_url="http://localhost") as client:
        assert client.post("/api/auth/setup", json=ADMIN).status_code == 201
        yield client, clock, mailer, app


def sign_in(client, identifier="admin", password=ADMIN["password"]):
    client.cookies.clear()
    body = {"identifier": identifier, "password": password}
    return client.post("/api/auth/login", json=body)


def invite(client):
    assert sign_in(client).status_code == 200
    response = client.post("/api/auth/invites", json={})
    assert response.status_code == 201, response.text
    client.cookies.clear()
    return response.json()


def register(client, **extra):
    return client.post("/api/auth/register", json={**NEWCOMER, **extra})


def test_invite_endpoints_are_administrator_only(lab):
    client, _, _, _ = lab
    target = (
        ("get", "/api/auth/invites"), ("post", "/api/auth/invites"),
        ("delete", "/api/auth/invites/1"),
    )
    for method, path in target:
        assert getattr(client, method)(path, headers={"Content-Type": "application/json"}
                                       ).status_code == 401
    assert sign_in(client).status_code == 200
    person = {"username": "pessoa", "email": "pessoa@example.com", "password": "Ab1@cd"}
    assert client.post("/api/auth/users", json={**person, "role": "user"}).status_code == 201
    assert sign_in(client, "pessoa", "Ab1@cd").status_code == 200
    for method, path in target:
        assert getattr(client, method)(path, headers={"Content-Type": "application/json"}
                                       ).status_code == 403


def test_user_is_the_default_and_admin_needs_an_invite(lab):
    client, _, mailer, _ = lab
    assert register(client).status_code == 201  # sem "role": vira usuário
    assert register(client, username="outro", email="outro@example.com",
                    role="user").status_code == 201
    # Escolher administrador sem código, ou com código a mais para usuário, é recusado.
    assert register(client, role="admin").status_code == 422
    assert register(client, role="admin", invite_code="   ").status_code == 422
    assert register(client, role="user", invite_code="ABCD-EFGH-JKMN").status_code == 422
    assert register(client, role="root").status_code == 422
    # Código que não existe: nega, registra e não cria a conta.
    wrong = register(client, username="intruso", email="intruso@example.com",
                     role="admin", invite_code="ABCD-EFGH-JKMN")
    assert wrong.status_code == 403 and "Código de convite" in wrong.json()["detail"]
    assert len(mailer.outbox) == 2
    assert sign_in(client).status_code == 200
    names = {u["username"]: u for u in client.get("/api/auth/users").json()["items"]}
    assert "intruso" not in names and names["nova"]["role"] == "user"
    assert "invite_rejected" in client.get("/api/auth/events").text


def test_valid_invite_creates_an_administrator_once(lab):
    client, _, mailer, _ = lab
    created = invite(client)
    code = created["code"]
    assert len(code) == 14 and code.count("-") == 2 and code == code.upper()
    # Sem hífens e em minúsculas também vale.
    typed = code.replace("-", "").lower()
    response = register(client, role="admin", invite_code=typed)
    assert response.status_code == 201
    blocked = sign_in(client, "nova", "Ab1@cd")
    assert blocked.status_code == 403  # ainda precisa confirmar o e-mail
    token = mailer.outbox[-1]["token"]
    assert client.post("/api/auth/confirm-email", json={"token": token}).status_code == 200
    assert sign_in(client, "nova", "Ab1@cd").status_code == 200
    assert client.get("/api/auth/users").status_code == 200  # é administrador de verdade
    # O mesmo código não serve de novo.
    second = register(client, username="segunda", email="segunda@example.com",
                      role="admin", invite_code=code)
    assert second.status_code == 403
    assert sign_in(client).status_code == 200
    assert client.get("/api/auth/invites").json()["items"] == []
    events = client.get("/api/auth/events").text
    assert "com convite de administrador" in events and code not in events


def test_invite_expires_can_be_revoked_and_is_capped(lab):
    client, clock, _, _ = lab
    expired = invite(client)
    clock[0] += INVITE_SECONDS + 1
    assert register(client, role="admin", invite_code=expired["code"]).status_code == 403

    revoked = invite(client)
    assert sign_in(client).status_code == 200
    listed = client.get("/api/auth/invites").json()["items"]
    assert [item["id"] for item in listed] == [revoked["id"]]
    assert "code" not in listed[0] and "code_hash" not in listed[0]
    assert client.delete(f"/api/auth/invites/{revoked['id']}",
                         headers={"Content-Type": "application/json"}).status_code == 200
    assert client.delete(f"/api/auth/invites/{revoked['id']}",
                         headers={"Content-Type": "application/json"}).status_code == 404
    client.cookies.clear()
    assert register(client, role="admin", invite_code=revoked["code"]).status_code == 403

    assert sign_in(client).status_code == 200
    for _ in range(MAX_OPEN_INVITES):
        assert client.post("/api/auth/invites", json={}).status_code == 201
    assert client.post("/api/auth/invites", json={}).status_code == 409


def test_failed_email_delivery_gives_the_invite_back(lab):
    client, _, mailer, _ = lab
    code = invite(client)["code"]
    mailer.fail = True
    assert register(client, role="admin", invite_code=code).status_code == 503
    mailer.fail = False
    assert register(client, role="admin", invite_code=code).status_code == 201


def test_invite_code_is_never_stored_in_plain_text(lab):
    client, _, _, app = lab
    code = invite(client)["code"]
    raw = code.replace("-", "")
    rows = app.state.accounts.db.execute("SELECT * FROM admin_invites").fetchall()
    stored = str(tuple(map(tuple, rows)))
    assert rows and raw not in stored and code not in stored
