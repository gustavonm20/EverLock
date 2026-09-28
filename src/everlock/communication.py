"""Canal remoto didático: prazo real, execução única e observações identificadas."""

import time
from datetime import UTC, datetime

from fastapi import HTTPException

from everlock.accounts import token_hash
from everlock.domain import Event


class Communication:
    def __init__(self, controller, accounts, clock=time.monotonic, wall_clock=time.time):
        self.controller, self.accounts = controller, accounts
        self.storage, self.db = controller.storage, controller.storage.connection
        self.clock, self.wall_clock = clock, wall_clock
        self.pending = {}
        self.observation = None
        self.observed_mono = None
        row = self.db.execute("SELECT * FROM network_state WHERE id=1").fetchone()
        self.internet = bool(row["internet_available"]) if row else True
        self.lan = bool(row["lan_available"]) if row else True
        self.delay = row["delay_seconds"] if row else 0.0
        with self.db:
            interrupted = self.db.execute(
                "SELECT id FROM remote_commands WHERE status IN ('requested','accepted')",
            ).fetchall()
            for row in interrupted:
                self.storage.finish_command(
                    row["id"], "failed", "restart_interrupted",
                    "O processo reiniciou. Confira o estado; o comando não será retomado.",
                    self.wall_clock(),
                )

    def _unavailable(self):
        if not self.controller.power.device_on:
            return "device_unavailable", "Dispositivo indisponível; use os controles locais."
        if not self.lan:
            return "lan_unavailable", "Rede local simulada indisponível. Comando não será retomado."
        if not self.internet:
            return "internet_unavailable", "Internet simulada cortada. Comando não será retomado."
        return None

    def _finish(self, command_id, status, code, message):
        with self.db:
            self.storage.finish_command(command_id, status, code, message, self.wall_clock())
        self.pending.pop(command_id, None)

    def _session_valid(self, row):
        return self.db.execute(
            """SELECT 1 FROM sessions s JOIN users u ON u.id=s.user_id
               WHERE s.token_hash=? AND s.user_id=? AND s.expires_at>?
               AND u.active=1 AND u.pending=0""",
            (row["session_hash"], row["user_id"], self.accounts.clock()),
        ).fetchone() is not None

    def tick(self):
        with self.controller.mutex:
            self.controller.tick()
            for command_id, (due, deadline) in list(self.pending.items()):
                row = self.db.execute("SELECT * FROM remote_commands WHERE id=?",
                                      (command_id,)).fetchone()
                if row is None or row["status"] != "requested":
                    self.pending.pop(command_id, None)
                    continue
                now = self.clock()
                unavailable = self._unavailable()
                if now >= deadline:
                    self._finish(command_id, "expired", "command_expired",
                                 "Prazo encerrado. O comando não foi executado.")
                elif not self._session_valid(row):
                    self._finish(command_id, "failed", "authorization_revoked",
                                 "A sessão ou autorização deixou de ser válida.")
                elif unavailable:
                    self._finish(command_id, "failed", *unavailable)
                elif now >= due:
                    with self.db:
                        self.storage.finish_command(command_id, "accepted", "accepted",
                                                    "Recebido pelo dispositivo virtual.",
                                                    self.wall_clock())
                    previous_actor = self.controller.actor
                    self.controller.actor = row["actor"]
                    try:
                        self.controller.remote_action(
                            row, lambda limit=deadline: self.clock() >= limit, self.wall_clock(),
                        )
                    except Exception:
                        # A decisão terminal e a porta são atômicas. Não repetir após erro.
                        self._finish(command_id, "failed", "execution_interrupted",
                                     "Não foi possível concluir a execução. Confira o estado.")
                        raise
                    finally:
                        self.controller.actor = previous_actor
                        self.pending.pop(command_id, None)
            if self._unavailable() is None:
                state = self.controller._status()
                self.observation = {"door": state["door"], "device": state["device"],
                                    "observed_at": datetime.fromtimestamp(
                                        self.wall_clock(), UTC).isoformat()}
                self.observed_mono = self.clock()

    def submit(self, payload, user, session_token):
        with self.controller.mutex:
            self.tick()
            command_id = str(payload.command_id)
            existing = self.db.execute("SELECT * FROM remote_commands WHERE id=?",
                                       (command_id,)).fetchone()
            if existing:
                if (existing["user_id"], existing["action"], existing["expected_version"],
                    existing["valid_for_seconds"]) != (
                    user["id"], payload.action, str(payload.expected_version),
                    payload.valid_for_seconds,
                ):
                    raise HTTPException(409, "Identificador já usado em outro comando.")
                return 200, {"duplicate": True, "command": self._public(existing)}
            recent = self.db.execute(
                "SELECT COUNT(*) FROM remote_commands WHERE user_id=? AND requested_at>?",
                (user["id"], self.wall_clock() - 60),
            ).fetchone()[0]
            if recent >= 20 or len(self.pending) >= 10:
                raise HTTPException(429, "Limite de comandos atingido. Aguarde antes de tentar.")
            now, real = self.clock(), self.wall_clock()
            with self.db:
                self.db.execute(
                    """INSERT INTO remote_commands
                       (id,action,user_id,actor,session_hash,expected_version,valid_for_seconds,
                        requested_at,expires_at,status,code,message)
                       VALUES (?,?,?,?,?,?,?,?,?,'requested','requested',?)""",
                    (command_id, payload.action, user["id"], user["username"],
                     token_hash(session_token), str(payload.expected_version),
                     payload.valid_for_seconds, real, real + payload.valid_for_seconds,
                     "Solicitado. A execução ainda não foi confirmada."),
                )
                self.db.execute(
                    "INSERT INTO command_transitions(command_id,status,occurred_at) VALUES (?,?,?)",
                    (command_id, "requested", real),
                )
            self.pending[command_id] = (now + self.delay, now + payload.valid_for_seconds)
            unavailable = self._unavailable()
            if unavailable:
                self._finish(command_id, "failed", *unavailable)
            row = self.db.execute("SELECT * FROM remote_commands WHERE id=?",
                                  (command_id,)).fetchone()
            return (409 if unavailable else 202), {"duplicate": False, "command": self._public(row)}

    def _public(self, row):
        result = {key: row[key] for key in (
            "id", "action", "actor", "status", "code", "message", "requested_at", "expires_at",
            "finished_at", "valid_for_seconds",
        )}
        result["transitions"] = [dict(item) for item in self.db.execute(
            "SELECT status,occurred_at FROM command_transitions WHERE command_id=? ORDER BY id",
            (row["id"],),
        )]
        return result

    def get(self, command_id, user):
        with self.controller.mutex:
            self.tick()
            row = self.db.execute("SELECT * FROM remote_commands WHERE id=?",
                                  (command_id,)).fetchone()
            if row is None or (user["role"] != "admin" and row["user_id"] != user["id"]):
                raise HTTPException(404, "Comando não encontrado.")
            return self._public(row)

    def snapshot(self, user):
        with self.controller.mutex:
            self.tick()
            condition, args = ("", ()) if user["role"] == "admin" else (
                "WHERE user_id=?", (user["id"],),
            )
            rows = self.db.execute(
                f"SELECT * FROM remote_commands {condition} ORDER BY rowid DESC LIMIT 20", args,
            ).fetchall()
            unavailable = self._unavailable()
            return {
                "mode": "simulation", "internet_available": self.internet,
                "lan_available": self.lan, "device_available": self.controller.power.device_on,
                "delay_seconds": self.delay, "channel_available": unavailable is None,
                "reason": unavailable[1] if unavailable else "Canal remoto simulado disponível.",
                "observation": self.observation,
                "observation_stale": unavailable is not None or self.observation is None,
                "observation_age_seconds": None if self.observed_mono is None
                else round(max(0, self.clock() - self.observed_mono), 1),
                "commands": [self._public(row) for row in rows],
            }

    def configure(self, payload):
        with self.controller.mutex:
            with self.db:
                self.db.execute(
                    "INSERT OR REPLACE INTO network_state VALUES (1,?,?,?)",
                    (payload.internet_available, payload.lan_available, payload.delay_seconds),
                )
            self.internet, self.lan, self.delay = (
                payload.internet_available, payload.lan_available, payload.delay_seconds,
            )
            self.controller.record(Event(
                "network_changed", "Cenário de rede atualizado",
                f"Internet: {'ligada' if self.internet else 'cortada'}; "
                f"rede local: {'ligada' if self.lan else 'cortada'}; "
                f"atraso: {self.delay:g} s reais.",
                "lab", "info",
            ))
            self.tick()
