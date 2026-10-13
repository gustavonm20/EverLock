"""SQLite: upgrades centralizados, atômicos e compatíveis com bancos anteriores."""

import sqlite3

SCHEMA_VERSION = 2
BASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS door_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    position TEXT NOT NULL CHECK (position IN ('open', 'closed')),
    revision INTEGER NOT NULL,
    updated_at TEXT NOT NULL
)

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    detail TEXT NOT NULL,
    source TEXT NOT NULL,
    outcome TEXT NOT NULL,
    created_at TEXT NOT NULL
)

CREATE TABLE IF NOT EXISTS simulation_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    power_json TEXT NOT NULL,
    timeline_json TEXT NOT NULL
)

CREATE TABLE IF NOT EXISTS remote_commands (
    id TEXT PRIMARY KEY, action TEXT NOT NULL, user_id INTEGER NOT NULL,
    actor TEXT NOT NULL, session_hash TEXT NOT NULL, expected_version TEXT NOT NULL,
    valid_for_seconds INTEGER NOT NULL, requested_at REAL NOT NULL,
    expires_at REAL NOT NULL, status TEXT NOT NULL,
    code TEXT NOT NULL, message TEXT NOT NULL, finished_at REAL
)

CREATE TABLE IF NOT EXISTS command_transitions (
    id INTEGER PRIMARY KEY, command_id TEXT NOT NULL,
    status TEXT NOT NULL, occurred_at REAL NOT NULL
)

CREATE INDEX IF NOT EXISTS command_owner_time
    ON remote_commands(user_id, requested_at)

CREATE TABLE IF NOT EXISTS network_state (
    id INTEGER PRIMARY KEY CHECK(id=1), internet_available INTEGER NOT NULL,
    lan_available INTEGER NOT NULL, delay_seconds REAL NOT NULL
)

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin', 'user')),
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1))
)

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    expires_at REAL NOT NULL
)

CREATE TABLE IF NOT EXISTS login_attempts (
    account TEXT NOT NULL, client TEXT NOT NULL, attempted_at REAL NOT NULL
)

CREATE TABLE IF NOT EXISTS account_events (
    id INTEGER PRIMARY KEY, type TEXT NOT NULL, actor TEXT,
    detail TEXT NOT NULL, created_at TEXT NOT NULL
)

CREATE TABLE IF NOT EXISTS registration_attempts (
    client TEXT NOT NULL, attempted_at REAL NOT NULL
)

CREATE TABLE IF NOT EXISTS password_resets (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    expires_at REAL NOT NULL
)

CREATE TABLE IF NOT EXISTS reset_attempts (
    client TEXT NOT NULL, attempted_at REAL NOT NULL
)

CREATE TABLE IF NOT EXISTS account_faces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    sealed BLOB NOT NULL,
    model TEXT NOT NULL,
    created_at REAL NOT NULL
)

CREATE INDEX IF NOT EXISTS account_face_owner ON account_faces(user_id)

CREATE TABLE IF NOT EXISTS admin_invites (
    id INTEGER PRIMARY KEY,
    code_hash TEXT NOT NULL UNIQUE,
    created_by TEXT NOT NULL,
    created_at REAL NOT NULL,
    expires_at REAL NOT NULL,
    used_by INTEGER,
    used_at REAL
)

CREATE TABLE IF NOT EXISTS email_confirmations (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    expires_at REAL NOT NULL
)

CREATE TABLE IF NOT EXISTS identities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    label TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0, 1)),
    consent_version TEXT NOT NULL,
    consent_recorded_by TEXT NOT NULL,
    consent_granted_at REAL NOT NULL,
    consent_revoked_at REAL,
    retention_days INTEGER NOT NULL,
    enrollment TEXT NOT NULL DEFAULT 'none'
        CHECK(enrollment IN ('none', 'simulated')),
    enrolled_at REAL,
    days TEXT NOT NULL,
    window_start INTEGER NOT NULL,
    window_end INTEGER NOT NULL,
    created_by TEXT NOT NULL,
    created_at REAL NOT NULL
)

CREATE UNIQUE INDEX IF NOT EXISTS identity_label ON identities(lower(label))

CREATE TABLE IF NOT EXISTS identity_events (
    id INTEGER PRIMARY KEY, type TEXT NOT NULL, actor TEXT,
    identity_id INTEGER, detail TEXT NOT NULL, created_at TEXT NOT NULL
)

CREATE TABLE IF NOT EXISTS face_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    identity_id INTEGER NOT NULL,
    sealed BLOB NOT NULL,
    model TEXT NOT NULL,
    created_at REAL NOT NULL
)

CREATE INDEX IF NOT EXISTS face_template_owner ON face_templates(identity_id)
"""


def _baseline(db: sqlite3.Connection) -> None:
    # execute (não executescript) mantém DDL e versão na mesma transação.
    for statement in BASE_SCHEMA.split("\n\n"):
        if statement.strip():
            db.execute(statement)
    additions = {
        "events": {"simulated_at": "REAL", "actor": "TEXT"},
        "users": {
            "pending": "INTEGER NOT NULL DEFAULT 0", "email": "TEXT",
            "email_confirmed": "INTEGER NOT NULL DEFAULT 1",
            "face_samples": "INTEGER NOT NULL DEFAULT 0", "face_enrolled_at": "REAL",
            "face_consent_version": "TEXT",
        },
        "sessions": {"method": "TEXT NOT NULL DEFAULT 'password'"},
        "identities": {"face_samples": "INTEGER NOT NULL DEFAULT 0"},
    }
    for table, columns in additions.items():
        existing = {row[1] for row in db.execute(f"PRAGMA table_info({table})")}
        for column, definition in columns.items():
            if column not in existing:
                db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
    db.execute("CREATE UNIQUE INDEX IF NOT EXISTS user_email ON users(email) "
               "WHERE email IS NOT NULL")


def _operational(db: sqlite3.Connection) -> None:
    db.execute("CREATE INDEX IF NOT EXISTS events_outcome_id ON events(outcome, id)")
    db.execute("CREATE INDEX IF NOT EXISTS events_source_id ON events(source, id)")
    db.execute("CREATE INDEX IF NOT EXISTS events_type_id ON events(type, id)")
    db.execute("ALTER TABLE identities ADD COLUMN subject_consent_at REAL")
    db.execute("ALTER TABLE identities ADD COLUMN subject_consent_version TEXT")


MIGRATIONS = (_baseline, _operational)


def migrate(db: sqlite3.Connection) -> None:
    """Migra uma vez, antes de criar serviços. Não altera banco de versão futura."""
    if db.in_transaction:
        raise RuntimeError("A migração exige uma conexão sem transação pendente.")
    db.execute("BEGIN IMMEDIATE")
    try:
        version = db.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise RuntimeError("Banco criado por uma versão mais nova do EverLock.")
        for index in range(version, SCHEMA_VERSION):
            MIGRATIONS[index](db)
            db.execute(f"PRAGMA user_version={index + 1}")
        db.commit()
    except Exception:
        db.rollback()
        raise
