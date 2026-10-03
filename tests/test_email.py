import os
import smtplib

import pytest
from fakes import RecordingMailer
from fastapi.testclient import TestClient

from everlock.accounts import CONFIRMATION_SECONDS, normalize_email
from everlock.app import create_app
from everlock.config import load_env_file
from everlock.mailer import Mailer, MailError, MailSettings

ADMIN = {"username": "admin", "email": "Admin@Example.com", "password": "Senha de testes1!"}
VISITOR = {"username": "visitante", "email": "visitante@example.com", "password": "Ab1@cd",
           "confirm_password": "Ab1@cd"}


@pytest.fixture
def lab(tmp_path):
    clock, mailer = [5000.0], RecordingMailer()
    app = create_app(tmp_path / "email.sqlite3", session_clock=lambda: clock[0], mailer=mailer)
    with TestClient(app, base_url="http://localhost") as client:
        assert client.post("/api/auth/setup", json=ADMIN).status_code == 201
        yield client, clock, mailer


def login(client, identifier, password):
    return client.post("/api/auth/login", json={"identifier": identifier, "password": password})


def register(client, **extra):
    return client.post("/api/auth/register", json={**VISITOR, **extra})


def test_email_validation_rules():
    typed = "  Nome.Sobrenome+lab@Exemplo.com.br "
    assert normalize_email(typed) == "nome.sobrenome+lab@exemplo.com.br"
    for bad in ("", "semarroba", "a@b", "a@@b.com", "a b@c.com", "a@-b.com", "a..b@c.com",
                "a@b.c", "@c.com", "a@c..com", "x" * 250 + "@c.com"):
        with pytest.raises(ValueError):
            normalize_email(bad)


def test_login_accepts_email_or_username_case_insensitively(lab):
    client, _, _ = lab
    for identifier in ("admin", "ADMIN", "admin@example.com", " Admin@Example.COM "):
        client.cookies.clear()
        assert login(client, identifier, ADMIN["password"]).status_code == 200, identifier
    assert login(client, "admin@example.com", "errada").status_code == 401
    assert login(client, "outro@example.com", ADMIN["password"]).status_code == 401
    assert client.post("/api/auth/login", json={"username": "admin",
                                               "password": ADMIN["password"]}).status_code == 422


def test_registration_needs_a_valid_unique_email(lab):
    client, _, _ = lab
    for bad in ("", "sem-arroba", "a@b", "a b@c.com"):
        assert register(client, email=bad).status_code == 422, bad
    without = {k: v for k, v in VISITOR.items() if k != "email"}
    assert client.post("/api/auth/register", json=without).status_code == 422
    assert register(client, email="ADMIN@example.com").status_code == 409
    assert register(client, username="admin").status_code == 409
    assert register(client).status_code == 201
    assert register(client, username="outro").status_code == 409  # mesmo e-mail


def test_confirmation_flow_is_single_use_and_blocks_login_until_confirmed(lab):
    client, _, mailer = lab
    assert register(client).status_code == 201
    message = mailer.outbox[-1]
    assert message["to"] == "visitante@example.com" and len(message["token"]) >= 40
    for who in ("visitante", "visitante@example.com"):
        blocked = login(client, who, VISITOR["password"])
        assert blocked.status_code == 403
        assert blocked.json()["detail"]["code"] == "email_unconfirmed"
    assert login(client, "visitante", "senha errada").status_code == 401  # não revela a conta
    assert client.post("/api/auth/confirm-email", json={"token": "x" * 43}).status_code == 400
    assert client.post("/api/auth/confirm-email", json={"token": "curto"}).status_code == 422
    confirm = {"token": message["token"]}
    assert client.post("/api/auth/confirm-email", json=confirm).status_code == 200
    assert client.post("/api/auth/confirm-email", json=confirm).status_code == 400
    assert login(client, "visitante@example.com", VISITOR["password"]).status_code == 200


def test_confirmation_expires_and_can_be_resent_only_by_the_owner(lab):
    client, clock, mailer = lab
    assert register(client).status_code == 201
    old = mailer.outbox[-1]["token"]
    clock[0] += CONFIRMATION_SECONDS + 1
    assert client.post("/api/auth/confirm-email", json={"token": old}).status_code == 400
    resend = {"identifier": "visitante", "password": VISITOR["password"]}
    assert client.post("/api/auth/resend-confirmation",
                       json={**resend, "password": "errada"}).status_code == 401
    assert len(mailer.outbox) == 1
    assert client.post("/api/auth/resend-confirmation", json=resend).status_code == 200
    fresh = mailer.outbox[-1]["token"]
    assert fresh != old
    assert client.post("/api/auth/confirm-email", json={"token": fresh}).status_code == 200
    assert client.post("/api/auth/resend-confirmation", json=resend).status_code == 409


def test_failed_delivery_undoes_the_registration(tmp_path):
    mailer = RecordingMailer(fail=True)
    app = create_app(tmp_path / "fail.sqlite3", mailer=mailer)
    with TestClient(app, base_url="http://localhost") as client:
        assert client.post("/api/auth/setup", json=ADMIN).status_code == 201
        failed = register(client)
        assert failed.status_code == 503 and "e-mail" in failed.json()["detail"]
        mailer.fail = False  # o nome de usuário e o e-mail voltam a ficar livres
        assert register(client).status_code == 201


def test_accounts_created_by_an_administrator_need_email_and_skip_confirmation(lab):
    client, _, _ = lab
    assert login(client, "admin", ADMIN["password"]).status_code == 200
    person = {"username": "pessoa", "password": "Ab1@cd", "role": "user"}
    assert client.post("/api/auth/users", json=person).status_code == 422
    assert client.post("/api/auth/users", json={**person, "email": "ruim"}).status_code == 422
    created = client.post("/api/auth/users", json={**person, "email": "pessoa@example.com"})
    assert created.status_code == 201
    client.cookies.clear()
    assert login(client, "pessoa@example.com", "Ab1@cd").status_code == 200


def test_console_delivery_prints_the_link_when_email_is_not_configured(tmp_path, capsys):
    app = create_app(tmp_path / "console.sqlite3", mailer=Mailer(None, "http://127.0.0.1:8000"))
    with TestClient(app, base_url="http://localhost") as client:
        assert client.post("/api/auth/setup", json=ADMIN).status_code == 201
        response = register(client)
    assert response.status_code == 201 and response.json()["delivery"] == "console"
    printed = capsys.readouterr().out
    assert "http://127.0.0.1:8000/#confirmar=" in printed
    assert "#confirmar=" not in response.text  # a API nunca devolve o link


def test_smtp_message_uses_starttls_login_and_a_fragment_link(monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            calls.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self, context):
            calls.append(("starttls",))

        def login(self, user, password):
            calls.append(("login", user, password))

        def send_message(self, message):
            calls.append(("send", message))

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    sender = "envio@exemplo.com"
    settings = MailSettings("smtp.exemplo.com", 587, sender, "segredo", sender)
    mailer = Mailer(settings, "http://127.0.0.1:8000/")
    assert mailer.send_confirmation("destino@exemplo.com", "maria", "TOKEN123") == "email"
    assert [call[0] for call in calls] == ["connect", "starttls", "login", "send"]
    message = calls[-1][1]
    assert message["To"] == "destino@exemplo.com" and message["From"] == "envio@exemplo.com"
    body = message.get_content()
    assert "http://127.0.0.1:8000/#confirmar=TOKEN123" in body and "segredo" not in body
    assert "segredo" not in repr(settings)

    def broken(*args, **kwargs):
        raise OSError("sem rede")

    monkeypatch.setattr(smtplib, "SMTP", broken)
    with pytest.raises(MailError):
        mailer.send_confirmation("destino@exemplo.com", "maria", "TOKEN123")


def test_environment_settings_and_env_file(monkeypatch, tmp_path):
    for key in ("HOST", "USER", "PASSWORD", "PORT", "FROM"):
        monkeypatch.delenv(f"EVERLOCK_SMTP_{key}", raising=False)
    assert not Mailer.from_environment().configured
    env_file = tmp_path / "everlock.env"
    env_file.write_text(
        "# comentário\nEVERLOCK_SMTP_HOST=smtp.exemplo.com\n"
        "EVERLOCK_SMTP_USER='envio@exemplo.com'\n"
        "EVERLOCK_SMTP_PASSWORD=segredo\nPATH=/nao/deve/mudar\n", encoding="utf-8",
    )
    monkeypatch.setenv("EVERLOCK_SMTP_HOST", "ja-definido.example")  # o ambiente vence o arquivo
    path_before = os.environ["PATH"]
    assert load_env_file(env_file) and not load_env_file(tmp_path / "nao-existe.env")
    mailer = Mailer.from_environment()
    assert mailer.configured and mailer.settings.host == "ja-definido.example"
    assert mailer.settings.username == mailer.settings.sender == "envio@exemplo.com"
    assert os.environ["PATH"] == path_before
    for key in ("EVERLOCK_SMTP_USER", "EVERLOCK_SMTP_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
