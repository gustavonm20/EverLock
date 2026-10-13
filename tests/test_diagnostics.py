import sqlite3
from dataclasses import asdict
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from everlock import __version__
from everlock.app import create_app
from everlock.faces import UnavailableEngine
from everlock.mailer import Mailer, MailSettings
from everlock.notifications import Notifier

ADMIN = {"username": "admin", "email": "admin@example.com", "password": "Teste seguro1!"}


@pytest.fixture
def lab(tmp_path):
    notifier = Notifier()
    app = create_app(
        tmp_path / "diagnostics.sqlite3", clock=lambda: 0,
        mailer=Mailer(None, "http://localhost"), notifier=notifier,
        face_engine=UnavailableEngine("private/path: secret engine exception"),
    )
    with TestClient(app, base_url="http://localhost") as client:
        assert client.post("/api/auth/setup", json=ADMIN).status_code == 201
        assert client.post("/api/auth/login", json={
            "identifier": ADMIN["username"], "password": ADMIN["password"],
        }).status_code == 200
        yield client, app, tmp_path


def items(response):
    assert response.status_code == 200
    return {item["id"]: item for item in response.json()["checks"]}


def test_diagnostics_requires_current_admin_session(lab):
    client, app, _ = lab
    assert client.get("/api/diagnostics").status_code == 200
    created = client.post("/api/auth/users", json={
        "username": "visitor", "email": "visitor@example.com",
        "password": ADMIN["password"], "role": "user",
    })
    assert created.status_code == 201
    client.post("/api/auth/logout", json={})
    assert client.get("/api/diagnostics").status_code == 401
    client.post("/api/auth/login", json={
        "identifier": "visitor", "password": ADMIN["password"],
    })
    assert client.get("/api/diagnostics").status_code == 403
    with app.state.controller.mutex, app.state.accounts.db:
        app.state.accounts.db.execute("UPDATE users SET active=0 WHERE username='visitor'")
    assert client.get("/api/diagnostics").status_code == 401


def test_diagnostics_is_read_only_and_distinguishes_optional_services(lab):
    client, app, path = lab
    controller = app.state.controller
    with controller.mutex:
        before = (asdict(controller.door), asdict(controller.power),
                  asdict(controller.timeline), controller.storage.connection.total_changes)
    # A requisição roda em outra thread; não manter a trava enquanto ela é atendida.
    response = client.get("/api/diagnostics")
    checks = items(response)
    with controller.mutex:
        after = (asdict(controller.door), asdict(controller.power),
                 asdict(controller.timeline), controller.storage.connection.total_changes)
    assert before == after
    assert not (path / "biometria.chave").exists()
    assert app.state.notifier.pending == 0
    assert app.state.notifier._worker is None
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["version"] == __version__
    assert response.json()["mode"] == "simulation"
    assert datetime.fromisoformat(response.json()["checked_at"]).tzinfo is not None
    assert checks["database"]["status"] == "ok"
    assert checks["face_engine"]["status"] == "attention"
    assert checks["email"]["status"] == checks["notifications"]["status"] == "info"
    assert "terminal" in checks["email"]["detail"]
    assert "private/path" not in response.text
    assert "secret engine exception" not in response.text


def test_diagnostics_does_not_contact_configured_services_or_expose_secrets(lab):
    client, app, _ = lab
    app.state.mailer = Mailer(MailSettings(
        "smtp.private.example", 587, "private-user", "private-password", "private-sender",
    ), "https://private.example")
    app.state.notifier = Notifier("https://private.example/private-token", "private-secret")
    app.state.recognition.engine = SimpleNamespace(available=True)
    app.state.face_login.vault = SimpleNamespace(available=False)
    response = client.get("/api/diagnostics")
    checks = items(response)
    assert checks["face_engine"]["status"] == "ok"
    assert checks["biometric_storage"]["status"] == "attention"
    assert "não verificado" in checks["email"]["summary"]
    assert checks["notifications"]["summary"] == "Configuradas"
    assert "private" not in response.text
    assert app.state.notifier._worker is None
    app.state.notifier.last_error = "private error message with credentials"
    response = client.get("/api/diagnostics")
    assert items(response)["notifications"]["status"] == "attention"
    assert "private" not in response.text


def test_diagnostics_handles_database_failure_without_exposing_exception(lab):
    client, app, _ = lab

    class BrokenConnection:
        def execute(self, query):
            raise sqlite3.OperationalError("private database path")

    storage = app.state.controller.storage
    connection = storage.connection
    try:
        storage.connection = BrokenConnection()
        response = client.get("/api/diagnostics")
        assert items(response)["database"]["status"] == "attention"
        assert "private" not in response.text
    finally:
        storage.connection = connection


@pytest.mark.parametrize("code,fragment", [
    ("models_missing", "não foram encontrados"),
    ("models_invalid", "não puderam ser carregados"),
    ("dependencies_missing", "precisam ser instaladas"),
])
def test_diagnostics_explains_safe_component_failures(lab, code, fragment):
    client, app, _ = lab
    app.state.recognition.engine.reason_code = code
    assert fragment in items(client.get("/api/diagnostics"))["face_engine"]["detail"]
