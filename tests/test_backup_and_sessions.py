import os
import sqlite3
import zipfile
from datetime import datetime

import pytest
from fakes import FakeFaceEngine
from fastapi.testclient import TestClient

from everlock.app import create_app
from everlock.backup import (
    DB_NAME,
    KEY_NAME,
    BackupError,
    create_backup,
    restore_backup,
)

ADMIN = {"username": "admin", "email": "admin@example.com", "password": "Senha de testes1!"}
JSON = {"Content-Type": "application/json"}
WHEN = datetime(2026, 10, 2, 12, 0, 0)


def make_data(folder, with_key=True):
    folder.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(folder / DB_NAME)
    connection.execute("CREATE TABLE t(x TEXT)")
    connection.execute("INSERT INTO t VALUES ('dado importante')")
    connection.commit()
    connection.close()
    if with_key:
        (folder / KEY_NAME).write_bytes(os.urandom(32))
    return folder


def read_value(folder):
    connection = sqlite3.connect(folder / DB_NAME)
    try:
        return connection.execute("SELECT x FROM t").fetchone()[0]
    finally:
        connection.close()


# --- cópia de segurança -------------------------------------------------------------------------


def test_plain_backup_roundtrip_keeps_database_and_key(tmp_path):
    source = make_data(tmp_path / "origem")
    archive = create_backup(source, tmp_path / "copias", now=WHEN)
    assert archive.name == "everlock-20261002-120000.zip"
    with zipfile.ZipFile(archive) as opened:
        assert sorted(opened.namelist()) == sorted([DB_NAME, KEY_NAME, "manifest.json"])
    target = tmp_path / "destino"
    assert restore_backup(archive, target) == sorted([DB_NAME, KEY_NAME])
    assert read_value(target) == "dado importante"
    assert (target / KEY_NAME).read_bytes() == (source / KEY_NAME).read_bytes()


def test_password_protected_backup_hides_content_and_checks_the_password(tmp_path):
    source = make_data(tmp_path / "origem")
    archive = create_backup(source, tmp_path / "copias", "senha-longa-1", now=WHEN)
    raw = archive.read_bytes()
    assert archive.suffix == ".elbak" and b"dado importante" not in raw
    assert (source / KEY_NAME).read_bytes() not in raw and b"SQLite format" not in raw
    target = tmp_path / "destino"
    with pytest.raises(BackupError, match="protegida por senha"):
        restore_backup(archive, target)
    with pytest.raises(BackupError, match="Senha incorreta"):
        restore_backup(archive, target, "outra-senha-9")
    assert not target.exists() or not (target / DB_NAME).exists()
    restore_backup(archive, target, "senha-longa-1")
    assert read_value(target) == "dado importante"
    with pytest.raises(BackupError, match="pelo menos 8"):
        create_backup(source, tmp_path / "copias", "curta", now=WHEN)


def test_tampered_or_foreign_archives_are_refused(tmp_path):
    source = make_data(tmp_path / "origem")
    archive = create_backup(source, tmp_path / "copias", "senha-longa-1", now=WHEN)
    raw = bytearray(archive.read_bytes())
    raw[-1] ^= 1
    archive.write_bytes(bytes(raw))
    with pytest.raises(BackupError, match="adulterado"):
        restore_backup(archive, tmp_path / "d1", "senha-longa-1")

    notzip = tmp_path / "lixo.zip"
    notzip.write_bytes(b"isto nao e um zip")
    with pytest.raises(BackupError, match="não é uma cópia"):
        restore_backup(notzip, tmp_path / "d2")
    with pytest.raises(BackupError, match="não encontrado"):
        restore_backup(tmp_path / "nao-existe.zip", tmp_path / "d3")

    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as bad:
        bad.writestr("../fora.txt", "x")
        bad.writestr("manifest.json", "{}")
    with pytest.raises(BackupError, match="não é o esperado"):
        restore_backup(evil, tmp_path / "d4")
    assert not (tmp_path / "fora.txt").exists()

    changed = tmp_path / "changed.zip"
    plain = create_backup(source, tmp_path / "copias2", now=WHEN)
    with zipfile.ZipFile(plain) as src, zipfile.ZipFile(changed, "w") as out:
        for info in src.infolist():
            data = src.read(info.filename)
            out.writestr(info.filename, data + b"x" if info.filename == KEY_NAME else data)
    with pytest.raises(BackupError, match="corrompida"):
        restore_backup(changed, tmp_path / "d5")


def test_restore_never_overwrites_without_force_and_keeps_a_reserve(tmp_path):
    source = make_data(tmp_path / "origem")
    archive = create_backup(source, tmp_path / "copias", now=WHEN)
    target = make_data(tmp_path / "destino")
    connection = sqlite3.connect(target / DB_NAME)
    connection.execute("UPDATE t SET x='dado atual'")
    connection.commit()
    connection.close()
    with pytest.raises(BackupError, match="--forcar"):
        restore_backup(archive, target)
    assert read_value(target) == "dado atual"
    restore_backup(archive, target, force=True, now=WHEN)
    assert read_value(target) == "dado importante"
    reserve = target / "antes-da-restauracao-20261002-120000"
    assert read_value(reserve) == "dado atual" and (reserve / KEY_NAME).exists()


def test_backup_of_a_running_database_and_missing_data(tmp_path):
    source = make_data(tmp_path / "origem", with_key=False)
    open_connection = sqlite3.connect(source / DB_NAME)  # "servidor" com o banco aberto
    open_connection.execute("INSERT INTO t VALUES ('novo')")
    open_connection.commit()
    archive = create_backup(source, tmp_path / "copias", now=WHEN)
    open_connection.close()
    with zipfile.ZipFile(archive) as opened:
        assert KEY_NAME not in opened.namelist()
    restore_backup(archive, tmp_path / "destino")
    connection = sqlite3.connect(tmp_path / "destino" / DB_NAME)
    assert connection.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 2
    connection.close()
    with pytest.raises(BackupError, match="Banco não encontrado"):
        create_backup(tmp_path / "vazio", tmp_path / "copias", now=WHEN)


# --- sessão aberta pelo rosto ---------------------------------------------------------------------


def b64(text):
    import base64
    return base64.b64encode(text.encode()).decode()


@pytest.fixture
def lab(tmp_path):
    app = create_app(tmp_path / "s.sqlite3", face_engine=FakeFaceEngine())
    with TestClient(app, base_url="http://localhost") as admin:
        assert admin.post("/api/auth/setup", json=ADMIN).status_code == 201
        credentials = {"identifier": "admin", "password": ADMIN["password"]}
        assert admin.post("/api/auth/login", json=credentials).status_code == 200
        body = {"password": ADMIN["password"], "consent": True,
                "images": [b64(f"PESSOA:ana:{n}") for n in range(5)]}
        assert admin.post("/api/auth/face/enroll", json=body).status_code == 201
        yield admin, TestClient(app, base_url="http://localhost"), app


def face_session(anonymous):
    challenge = anonymous.post("/api/auth/face/challenge", json={}).json()
    sign = 1 if challenge["direction"] == "left" else -1
    body = {"challenge_id": challenge["challenge_id"], "front": b64("PESSOA:ana:front:0"),
            "turned": [b64(f"PESSOA:ana:t{n}:{sign * 0.3}") for n in range(3)]}
    assert anonymous.post("/api/auth/face/login", json=body).status_code == 200


def test_face_session_cannot_create_admins_or_invites_but_keeps_everything_else(lab):
    admin, anonymous, _ = lab
    person = {"username": "pessoa", "email": "pessoa@example.com", "password": "Ab1@cd"}
    face_session(anonymous)
    assert anonymous.get("/api/auth/session").json()["user"]["role"] == "admin"
    assert anonymous.get("/api/status").status_code == 200  # uso normal continua
    assert anonymous.get("/api/auth/users").status_code == 200
    assert anonymous.post("/api/auth/users", json={**person, "role": "user"}).status_code == 201
    blocked = [
        anonymous.post("/api/auth/invites", json={}),
        anonymous.post("/api/auth/users", json={**person, "username": "outro",
                                                "email": "o@example.com", "role": "admin"}),
        anonymous.patch("/api/auth/users/2", json={"role": "admin", "active": True}),
    ]
    for response in blocked:
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "password_required"
        assert "senha" in response.json()["detail"]["message"]
    demote = anonymous.patch("/api/auth/users/2", json={"role": "user", "active": False})
    assert demote.status_code == 200  # desativar e rebaixar não é escalada
    assert "face_session_restricted" in anonymous.get("/api/auth/events").text


def test_password_session_keeps_full_admin_powers(lab):
    admin, _, _ = lab
    assert admin.post("/api/auth/invites", json={}).status_code == 201
    person = {"username": "nova", "email": "nova@example.com", "password": "Ab1@cd"}
    assert admin.post("/api/auth/users", json={**person, "role": "admin"}).status_code == 201
    promote = admin.patch("/api/auth/users/2", json={"role": "admin", "active": True})
    assert promote.status_code == 200


def test_logging_in_with_the_password_replaces_a_face_session(lab):
    admin, anonymous, _ = lab
    face_session(anonymous)
    assert anonymous.post("/api/auth/invites", json={}).status_code == 403
    credentials = {"identifier": "admin", "password": ADMIN["password"]}
    assert anonymous.post("/api/auth/login", json=credentials).status_code == 200
    assert anonymous.post("/api/auth/invites", json={}).status_code == 201


def test_old_sessions_table_gets_the_method_column(tmp_path):
    path = tmp_path / "old.sqlite3"
    connection = sqlite3.connect(path)
    connection.executescript(
        "CREATE TABLE sessions (token_hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, "
        "expires_at REAL NOT NULL); INSERT INTO sessions VALUES ('a', 1, 9e12);")
    connection.commit()
    connection.close()
    app = create_app(path, face_engine=FakeFaceEngine())
    with TestClient(app, base_url="http://localhost"):
        columns = [row[1] for row in app.state.accounts.db.execute("PRAGMA table_info(sessions)")]
        assert "method" in columns
        kept = app.state.accounts.db.execute("SELECT method FROM sessions").fetchone()
        assert kept[0] == "password"  # sessões antigas contam como entradas por senha
