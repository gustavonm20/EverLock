"""Estado e eventos são gravados juntos, em uma transação SQLite."""

import sqlite3
from pathlib import Path

from everlock.domain import Door, Event


class Storage:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False, timeout=5)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript("""
            PRAGMA journal_mode=WAL;
            PRAGMA synchronous=FULL;
            CREATE TABLE IF NOT EXISTS door_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                position TEXT NOT NULL CHECK (position IN ('open', 'closed')),
                revision INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                title TEXT NOT NULL,
                detail TEXT NOT NULL,
                source TEXT NOT NULL,
                outcome TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
        """)

    def load(self) -> Door:
        row = self.connection.execute("SELECT * FROM door_state WHERE id=1").fetchone()
        if row is None:
            return Door()
        # A liberação é transitória: nunca é restaurada após reinicialização.
        return Door(
            position=row["position"], revision=row["revision"], updated_at=row["updated_at"],
        )

    def save(self, door: Door, event: Event) -> None:
        with self.connection:
            self.connection.execute(
                """INSERT INTO door_state (id, position, revision, updated_at) VALUES (1, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET position=excluded.position,
                   revision=excluded.revision, updated_at=excluded.updated_at""",
                (door.position, door.revision, door.updated_at),
            )
            self.connection.execute(
                """INSERT INTO events (type, title, detail, source, outcome, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (event.type, event.title, event.detail, event.source,
                 event.outcome, door.updated_at),
            )

    def events(self, limit: int) -> list[dict]:
        return [
            dict(row)
            for row in self.connection.execute(
                "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        ]

    def close(self) -> None:
        self.connection.close()
