import pytest
from fastapi.testclient import TestClient

from everlock.accounts import SESSION_SECONDS, password_hash, password_matches, validate_password
from everlock.app import create_app

PASSWORD = "Senha isolada para testes1!"
ADMIN = {"username": "admin", "password": PASSWORD}


@pytest.fixture
def accounts(tmp_path):
    real = [1000.0]
    app = create_app(tmp_path / "accounts.sqlite3", session_clock=lambda: real[0])
    with TestClient(app, base_url="http://localhost") as client:
        yield client, real, app


def login(client, username="admin", password=PASSWORD):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def prepare(client):
    assert client.post("/api/auth/setup", json=ADMIN).status_code == 201
    assert login(client).status_code == 200


def test_first_setup_only_once_and_all_simulation_routes_require_session(accounts):
    client, _, _ = accounts
    assert client.get("/api/auth/session").json()["setup_required"]
    assert client.get("/api/status").status_code == 401
    assert client.get("/api/events").status_code == 401
    assert client.get("/api/ups").status_code == 401
    for path, body in [("actions", {"action": "exit"}),
                       ("simulation/clock", {"paused": True}),
                       ("simulation/power", {"mains_available": False}),
                       ("simulation/power/config", {})]:
        assert client.post(f"/api/{path}", json=body).status_code == 401
    prepare(client)
    assert client.post("/api/auth/setup", json=ADMIN).status_code == 409
    assert not client.get("/api/auth/session").json()["setup_required"]


def test_passwords_are_salted_and_unknown_user_denied(accounts):
    first, second = password_hash(PASSWORD), password_hash(PASSWORD)
    assert first != second and PASSWORD not in first
    assert password_matches(PASSWORD, first)
    assert not password_matches("outra senha bastante longa", first)
    client, _, _ = accounts
    prepare(client)
    assert login(client, "nobody").status_code == 401


def test_cookie_and_session_storage_contain_no_plain_token(accounts):
    client, _, app = accounts
    prepare(client)
    response = login(client)
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    token = client.cookies.get("everlock_session")
    with app.state.controller.mutex:
        rows = app.state.accounts.db.execute("SELECT * FROM sessions").fetchall()
        assert len(rows) == 1 and token != rows[0]["token_hash"]
    assert client.post("/api/auth/logout", json={}).status_code == 200
    client.cookies.set("everlock_session", token)
    assert client.get("/api/status").status_code == 401


def test_virtual_time_does_not_expire_or_extend_real_session(accounts):
    client, real, _ = accounts
    prepare(client)
    client.post("/api/simulation/clock", json={"paused": True})
    client.post("/api/simulation/clock", json={"advance_seconds": 86400})
    assert client.get("/api/status").status_code == 200
    real[0] += SESSION_SECONDS
    assert client.get("/api/status").status_code == 401


def test_user_permissions_and_immediate_revocation(accounts):
    client, _, _ = accounts
    prepare(client)
    client.post("/api/auth/users", json={"username": "pessoa", "password": PASSWORD})
    admin_token = client.cookies.get("everlock_session")
    client.cookies.clear()
    login(client, "pessoa")
    user_token = client.cookies.get("everlock_session")
    assert client.get("/api/status").status_code == 200
    assert client.post("/api/actions", json={"action": "unlock"}).status_code == 403
    assert client.post("/api/actions", json={"action": "exit"}).status_code == 200
    for path in ("events", "auth/users", "auth/events"):
        assert client.get(f"/api/{path}").status_code == 403
    assert client.post("/api/simulation/power/config", json={}).status_code == 403
    assert client.post("/api/actions", json={"action": "key_entry"}).status_code == 403
    client.cookies.clear()
    client.cookies.set("everlock_session", admin_token)
    users = client.get("/api/auth/users").json()["items"]
    person = next(x for x in users if x["username"] == "pessoa")
    assert client.patch(f"/api/auth/users/{person['id']}",
                        json={"role": "user", "active": False}).status_code == 200
    events = client.get("/api/events").json()["items"]
    assert any(e["type"] == "exit" and e["actor"] == "pessoa" for e in events)
    client.cookies.clear()
    client.cookies.set("everlock_session", user_token)
    assert client.post("/api/actions", json={"action": "unlock"}).status_code == 401
    assert login(client, "pessoa").status_code == 401


def test_last_administrator_cannot_be_removed(accounts):
    client, _, _ = accounts
    prepare(client)
    for update in ({"role": "user", "active": True}, {"role": "admin", "active": False}):
        assert client.patch("/api/auth/users/1", json=update).status_code == 409
    assert client.get("/api/auth/session").json()["user"]["role"] == "admin"


def test_password_change_revokes_session_and_preserves_audit(accounts):
    client, _, _ = accounts
    prepare(client)
    replacement = "Nova senha somente teste1!"
    assert client.post("/api/auth/password", json={
        "current_password": "Senha incorreta para teste!", "new_password": replacement,
    }).status_code == 403
    assert client.post("/api/auth/password", json={
        "current_password": PASSWORD, "new_password": replacement,
    }).status_code == 200
    assert client.get("/api/status").status_code == 401
    assert login(client).status_code == 401
    assert login(client, password=replacement).status_code == 200
    text = client.get("/api/auth/events").text
    assert "password_changed" in text
    assert PASSWORD not in text and replacement not in text


def test_login_rate_limit_uses_real_time(accounts):
    client, real, _ = accounts
    prepare(client)
    for _ in range(5):
        assert login(client, password="Senha errada para testes!").status_code == 401
    assert login(client).status_code == 429
    real[0] += 301
    assert login(client).status_code == 200


def test_setup_rejects_cross_origin_and_never_echoes_password(accounts):
    client, _, _ = accounts
    assert client.post("/api/auth/setup", json=ADMIN,
                       headers={"Origin": "https://other.example"}).status_code == 403
    response = client.post("/api/auth/setup", json={"username": "x", "password": "secreta"})
    assert response.status_code == 422 and "secreta" not in response.text


def test_duplicate_account_and_invalid_roles_are_rejected(accounts):
    client, _, _ = accounts
    prepare(client)
    assert client.post("/api/auth/users", json=ADMIN).status_code == 409
    assert client.patch("/api/auth/users/1",
                        json={"role": "root", "active": True}).status_code == 422
    assert client.patch("/api/auth/users/999",
                        json={"role": "user", "active": True}).status_code == 404


def test_external_ups_never_reports_simulated_battery_as_real(accounts):
    client, real, _ = accounts
    prepare(client)
    before = client.get("/api/ups").json()
    assert before["observation"] is None
    assert before["status"] == "not_monitored"
    assert before["source"] == "external_equipment"
    assert before["controls_available"] is False
    client.post("/api/simulation/clock", json={"paused": True})
    client.post("/api/simulation/power", json={"mains_available": False})
    client.post("/api/simulation/clock", json={"advance_seconds": 86400})
    real[0] += 15
    assert client.get("/api/ups").json() == before


def test_accounts_and_revocations_survive_restart(tmp_path):
    path = tmp_path / "restart.sqlite3"
    with TestClient(create_app(path), base_url="http://localhost") as client:
        prepare(client)
        token = client.cookies.get("everlock_session")
    with TestClient(create_app(path), base_url="http://localhost") as client:
        client.cookies.set("everlock_session", token)
        assert client.get("/api/status").status_code == 200
        assert client.post("/api/auth/setup", json=ADMIN).status_code == 409
        assert client.post("/api/auth/logout", json={}).status_code == 200
    with TestClient(create_app(path), base_url="http://localhost") as client:
        client.cookies.set("everlock_session", token)
        assert client.get("/api/status").status_code == 401


@pytest.mark.parametrize("password", ["Ab1!x", "abcdef1!", "ABCDEF1!", "Abcdef!", "Abcdef1"])
def test_password_policy_rejects_each_missing_requirement(password):
    with pytest.raises(ValueError, match="6 caracteres"):
        validate_password(password)


def test_six_character_and_long_passwords_work_without_truncation(accounts):
    client, _, _ = accounts
    short = {"username": "admin", "password": "Ab1.cd"}
    assert client.post("/api/auth/setup", json=short).status_code == 201
    assert login(client, password=short["password"]).status_code == 200
    long_password = "Ábc1?" + "x" * 10000
    assert client.post("/api/auth/password", json={
        "current_password": short["password"], "new_password": long_password,
    }).status_code == 200
    assert login(client, password=long_password).status_code == 200
    assert login(client, password=long_password[:-1]).status_code == 401


def test_registration_requires_approval_and_cannot_choose_privileges(accounts):
    client, _, _ = accounts
    prepare(client)
    admin_token = client.cookies.get("everlock_session")
    client.post("/api/auth/logout", json={})
    data = {"username": "Visitante", "password": "Ab1@cd", "confirm_password": "Ab1@cd"}
    assert client.post("/api/auth/register", json={**data, "role": "admin"}).status_code == 422
    assert client.post("/api/auth/register", json={**data, "active": True}).status_code == 422
    assert client.post("/api/auth/register", json=data).status_code == 201
    assert client.get("/api/status").status_code == 401
    assert login(client, "visitante", "Ab1@cd").status_code == 401
    assert login(client).status_code == 200
    assert client.cookies.get("everlock_session") != admin_token
    pending = next(x for x in client.get("/api/auth/users").json()["items"]
                   if x["username"] == "visitante")
    assert pending["pending"] == 1 and not pending["active"] and pending["role"] == "user"
    assert client.patch(f"/api/auth/users/{pending['id']}",
                        json={"role": "user", "active": True}).status_code == 200
    assert "registration_requested" in client.get("/api/auth/events").text
    client.cookies.clear()
    assert login(client, "visitante", "Ab1@cd").status_code == 200
    assert client.get("/api/status").status_code == 200
    assert client.get("/api/auth/users").status_code == 403


def test_registration_setup_confirmation_and_duplicate_guards(accounts):
    client, _, _ = accounts
    data = {"username": "visitante", "password": "Ab1$cd", "confirm_password": "Ab1$cd"}
    assert client.post("/api/auth/register", json=data).status_code == 409
    prepare(client)
    response = client.post("/api/auth/register", json={**data, "confirm_password": "diferente"})
    assert response.status_code == 422 and "Ab1$cd" not in response.text
    assert client.post("/api/auth/register", json=data,
                       headers={"Origin": "https://other.example"}).status_code == 403
    assert client.post("/api/auth/register", json=data).status_code == 201
    assert client.post("/api/auth/register", json=data).status_code == 409
    for path in ("setup", "register", "users"):
        weak = {"username": "outrapessoa", "password": "abcdef"}
        if path == "register":
            weak["confirm_password"] = "abcdef"
        assert client.post(f"/api/auth/{path}", json=weak).status_code == 422


def test_registration_limit_and_existing_password_compatibility(accounts):
    client, real, app = accounts
    # Uma conta criada antes da nova política continua conseguindo entrar.
    app.state.accounts.setup("admin", "Senha antiga sem numero!")
    assert login(client, password="Senha antiga sem numero!").status_code == 200
    data = {"username": "visitante", "password": "Ab1!cd", "confirm_password": "Ab1!cd"}
    assert client.post("/api/auth/register", json=data).status_code == 201
    for _ in range(4):
        assert client.post("/api/auth/register", json=data).status_code == 409
    assert client.post("/api/auth/register", json=data).status_code == 429
    real[0] += 301
    assert client.post("/api/auth/register", json={**data, "username": "outra"}).status_code == 201


def test_console_recovery_uses_same_policy_and_revokes_sessions(tmp_path, monkeypatch):
    from everlock.recover_admin import main

    path = tmp_path / "everlock.sqlite3"
    with TestClient(create_app(path), base_url="http://localhost") as client:
        prepare(client)
        token = client.cookies.get("everlock_session")
    monkeypatch.setenv("EVERLOCK_DATA_DIR", str(tmp_path))
    monkeypatch.setattr("sys.argv", ["recover_admin", "admin"])
    monkeypatch.setattr("getpass.getpass", lambda _: "abcdef")
    with pytest.raises(SystemExit, match="6 caracteres"):
        main()
    monkeypatch.setattr("getpass.getpass", lambda _: "Ab1?cd")
    main()
    with TestClient(create_app(path), base_url="http://localhost") as client:
        client.cookies.set("everlock_session", token)
        assert client.get("/api/status").status_code == 401
        assert login(client, password="Ab1?cd").status_code == 200
        assert "admin_recovered" in client.get("/api/auth/events").text
