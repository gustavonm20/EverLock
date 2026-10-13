import sqlite3

import pytest

from everlock import database
from everlock.storage import Storage


def test_legacy_database_upgrade_preserves_rows_and_is_idempotent(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT UNIQUE, "
                   "password_hash TEXT, role TEXT, active INTEGER DEFAULT 1)")
        db.execute("INSERT INTO users VALUES (7, 'antigo', 'hash-original', 'admin', 1)")
        db.execute("CREATE TABLE events(id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT, "
                   "title TEXT, detail TEXT, source TEXT, outcome TEXT, created_at TEXT)")
        db.execute("INSERT INTO events VALUES (9, 'test', 'Título', '', 'lab', 'info', '2026')")
    for _ in range(2):
        storage = Storage(path)
        db = storage.connection
        assert db.execute("PRAGMA user_version").fetchone()[0] == database.SCHEMA_VERSION
        row = db.execute("SELECT * FROM users WHERE id=7").fetchone()
        assert row["password_hash"] == "hash-original" and row["email"] is None
        assert row["email_confirmed"] == 1 and row["pending"] == 0
        assert storage.events(10)[0]["id"] == 9
        assert storage.events(10)[0]["actor"] is None
        storage.close()


def test_upgrade_failure_rolls_back_schema_and_version(tmp_path, monkeypatch):
    db = sqlite3.connect(tmp_path / "atomic.sqlite3")

    def fail(connection):
        connection.execute("CREATE TABLE partial (id INTEGER)")
        raise RuntimeError("injected")

    monkeypatch.setattr(database, "MIGRATIONS", (database._baseline, fail))
    with pytest.raises(RuntimeError, match="injected"):
        database.migrate(db)
    assert db.execute("PRAGMA user_version").fetchone()[0] == 0
    assert db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []
    db.close()


def test_future_version_is_refused_without_changing_data(tmp_path):
    path = tmp_path / "future.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA user_version=999")
        db.execute("CREATE TABLE future (value TEXT)")
        db.execute("INSERT INTO future VALUES ('preservado')")
    with pytest.raises(RuntimeError, match="mais nova"):
        Storage(path)
    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 999
        assert db.execute("SELECT * FROM future").fetchall() == [("preservado",)]
