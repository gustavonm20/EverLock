"""Estado e eventos são gravados juntos, em uma transação SQLite."""

import json
import math
import sqlite3
from dataclasses import asdict
from pathlib import Path

from everlock.database import migrate
from everlock.domain import Door, Event
from everlock.energy import Power, PowerConfig
from everlock.simulation import Timeline


class Storage:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path, check_same_thread=False, timeout=5)
        self.connection.row_factory = sqlite3.Row
        try:
            migrate(self.connection)
            self.connection.execute("PRAGMA journal_mode=WAL")
            self.connection.execute("PRAGMA synchronous=FULL")
        except Exception:
            self.connection.close()
            raise

    def load(self) -> Door:
        row = self.connection.execute("SELECT * FROM door_state WHERE id=1").fetchone()
        if row is None:
            return Door()
        # A liberação é transitória: nunca é restaurada após reinicialização.
        return Door(
            position=row["position"], revision=row["revision"], updated_at=row["updated_at"],
        )

    def load_simulation(self) -> tuple[Power, Timeline]:
        row = self.connection.execute("SELECT * FROM simulation_state WHERE id=1").fetchone()
        if row is None:
            return Power(), Timeline()
        values = json.loads(row["power_json"])
        config = PowerConfig(**values.pop("config"))
        power = Power(config=config, **values)
        timeline = Timeline(**json.loads(row["timeline_json"]))
        if not math.isfinite(power.stored_wh) or not 0 <= power.stored_wh <= config.capacity_wh:
            raise ValueError("Carga virtual salva fora dos limites.")
        if not math.isfinite(timeline.elapsed_seconds) or timeline.elapsed_seconds < 0:
            raise ValueError("Tempo virtual salvo fora dos limites.")
        # Tempo com o processo fechado não é simulado. Retorno sempre pausado e em 1x.
        timeline.paused = True
        timeline.speed = 1
        return power, timeline

    def save(self, door: Door, events: list[Event], power: Power, timeline: Timeline,
             command_result: tuple[str, str, str, str, float] | None = None) -> None:
        with self.connection:
            self.connection.execute(
                """INSERT INTO door_state (id, position, revision, updated_at) VALUES (1, ?, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET position=excluded.position,
                   revision=excluded.revision, updated_at=excluded.updated_at""",
                (door.position, door.revision, door.updated_at),
            )
            self.connection.execute(
                """INSERT INTO simulation_state VALUES (1, ?, ?)
                   ON CONFLICT(id) DO UPDATE SET power_json=excluded.power_json,
                   timeline_json=excluded.timeline_json""",
                (json.dumps(asdict(power)), json.dumps(asdict(timeline))),
            )
            self.connection.executemany(
                """INSERT INTO events
                   (type, title, detail, source, outcome, created_at, simulated_at, actor)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                [(event.type, event.title, event.detail, event.source, event.outcome,
                  door.updated_at, event.simulated_at, event.actor) for event in events],
            )
            if command_result is not None:
                self.finish_command(*command_result)

    def finish_command(self, command_id, status, code, message, now):
        changed = self.connection.execute(
            """UPDATE remote_commands SET status=?, code=?, message=?, finished_at=?
               WHERE id=? AND status IN ('requested', 'accepted')""",
            (status, code, message, None if status == "accepted" else now, command_id),
        )
        if changed.rowcount:
            self.connection.execute(
                "INSERT INTO command_transitions(command_id,status,occurred_at) VALUES (?,?,?)",
                (command_id, status, now),
            )

    def events(self, limit: int) -> list[dict]:
        return [
            dict(row)
            for row in self.connection.execute(
                "SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        ]

    def search_events(self, limit: int, where: str, params: list) -> list[dict]:
        """`where` vem de `history.build_where`: fragmentos fixos, valores em parâmetros."""
        query = f"SELECT * FROM events{where} ORDER BY id DESC LIMIT ?"
        return [dict(row) for row in self.connection.execute(query, (*params, limit)).fetchall()]

    def close(self) -> None:
        self.connection.close()
