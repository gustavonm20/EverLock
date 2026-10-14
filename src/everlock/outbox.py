"""Avisos persistentes de melhor esforço, independentes da autorização da porta.

Persistem apenas metadados técnicos, por até 24 h. Uma queda depois do recebimento
e antes da confirmação local pode duplicar um aviso: o receptor deve deduplicar pelo id.
Não é uma outbox transacional do domínio; uma falha de disco pode perder um aviso.
"""

import hashlib
import json
import os
import sqlite3
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from everlock import __version__
from everlock.notifications import LEVELS, DeliveryError, Notifier, classify

TTL_SECONDS = 24 * 3600


class DurableNotifier(Notifier):
    def __init__(self, store_path: Path, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.db = None
        self.capacity = self.queue.maxsize
        # Não guarda URL, caminho do webhook nem segredo; mudar o destino descarta pendências.
        self.destination_key = hashlib.sha256((self.url + "\0" + self.secret).encode()).hexdigest()
        if not self.configured:
            return
        try:
            store_path.parent.mkdir(parents=True, exist_ok=True)
            self.db = sqlite3.connect(store_path, timeout=0.1, check_same_thread=False)
            self.db.row_factory = sqlite3.Row
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.execute("PRAGMA synchronous=FULL")
            with self.db:
                self.db.execute("""CREATE TABLE IF NOT EXISTS notification_outbox (
                    id TEXT PRIMARY KEY, destination TEXT NOT NULL, body BLOB NOT NULL,
                    expires_at REAL NOT NULL, next_attempt REAL NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0
                )""")
                self.db.execute("DELETE FROM notification_outbox WHERE destination != ? "
                                "OR expires_at <= ?", (self.destination_key, time.time()))
            self.pending = self.db.execute("SELECT count(*) FROM notification_outbox").fetchone()[0]
        except (OSError, sqlite3.Error):
            if self.db is not None:
                self.db.close()
            self.db = None
            self.reason = "Fila local indisponível. Os avisos não serão enviados."
            return
        self._worker = threading.Thread(target=self._run_persistent, name="everlock-outbox",
                                        daemon=True)
        self._worker.start()

    @classmethod
    def from_environment(cls, store_path: Path) -> "DurableNotifier":
        return cls(store_path, os.getenv("EVERLOCK_WEBHOOK_URL", ""),
                   os.getenv("EVERLOCK_WEBHOOK_SECRET", ""),
                   os.getenv("EVERLOCK_WEBHOOK_LEVEL", "warning").strip().lower())

    def publish(self, kind, title, detail, source="lab", outcome="info", actor=None, *,
                force=False) -> bool:
        if not self.configured or self.stop.is_set():
            return False
        severity = classify(kind, outcome)
        if not force and LEVELS[severity] < LEVELS[self.level]:
            return False
        event_id, now = uuid4().hex, time.time()
        # Sem nomes, títulos livres, dados biométricos ou detalhes de contas no disco/serviço.
        payload = {"app": "EverLock", "version": __version__, "id": event_id,
                   "type": kind, "severity": severity, "source": source, "outcome": outcome,
                   "title": "Evento do laboratório", "detail": "Consulte o histórico local.",
                   "actor": None, "occurred_at": datetime.now(UTC).isoformat()}
        with self.lock:
            if self.stop.is_set():
                return False
            try:
                with self.db:
                    purged = self._purge(now)
                    accepted = self.pending - purged < self.capacity
                    if accepted:
                        self.db.execute("INSERT INTO notification_outbox "
                                        "(id,destination,body,expires_at,next_attempt) "
                                        "VALUES (?,?,?,?,?)",
                                        (event_id, self.destination_key,
                                         json.dumps(payload).encode(), now + TTL_SECONDS, now))
                # Só contabiliza alterações que o SQLite confirmou; rollback preserva a fila.
                self.pending += int(accepted) - purged
                self.dropped += purged + int(not accepted)
            except sqlite3.Error:
                self.dropped += 1
                self.last_error = "Não foi possível registrar o aviso na fila local."
                return False
        return accepted

    def _purge(self, now):
        return self.db.execute("DELETE FROM notification_outbox WHERE expires_at <= ?",
                               (now,)).rowcount

    def _run_persistent(self):
        try:
            while not self.stop.is_set():
                try:
                    with self.lock:
                        with self.db:
                            purged = self._purge(time.time())
                            row = self.db.execute(
                                "SELECT * FROM notification_outbox WHERE next_attempt <= ? "
                                "ORDER BY next_attempt, id LIMIT 1", (time.time(),),
                            ).fetchone()
                            if row:
                                # Reserva antes da rede; o orçamento sobrevive a reinícios.
                                self.db.execute(
                                    "UPDATE notification_outbox SET attempts=attempts+1, "
                                    "next_attempt=? WHERE id=?", (time.time() + 30, row["id"]),
                                )
                        self.pending -= purged
                        self.dropped += purged
                    if row:
                        self._send_pending(row)
                    else:
                        self.stop.wait(0.1)
                except sqlite3.Error:
                    with self.lock:
                        self.last_error = "Falha ao consultar a fila local de avisos."
                    self.stop.wait(1)
        finally:
            with self.lock:
                self.db.close()

    def _send_pending(self, row):
        error = None
        if row["attempts"] > len(self.retry_delays):
            error = DeliveryError("Limite de tentativas atingido após reinício.", False)
        else:
            try:
                self.sender(bytes(row["body"]))
            except DeliveryError as problem:
                error = problem
            except Exception:
                error = DeliveryError("Falha interna ao entregar o aviso.", False)
        with self.lock:
            if error and error.retry and row["attempts"] < len(self.retry_delays):
                with self.db:
                    self.db.execute("UPDATE notification_outbox SET next_attempt=? WHERE id=?",
                                    (time.time() + self.retry_delays[row["attempts"]], row["id"]))
                self.last_error = "Entrega temporariamente indisponível; nova tentativa agendada."
                return
            with self.db:
                removed = self.db.execute("DELETE FROM notification_outbox WHERE id=?",
                                          (row["id"],)).rowcount
            self.pending -= removed
            if error:
                self.failed += 1
                self.last_error = "Aviso encerrado sem confirmação de entrega."
            else:
                self.sent += 1
                self.last_error = None
                self.last_ok_at = datetime.now(UTC).isoformat()

    def close(self):
        with self.lock:
            self.stop.set()
        if self._worker is not None:
            self._worker.join(timeout=self.timeout + 1)

    def status(self):
        result = super().status()
        result.update({"persistent": self.db is not None, "retention_hours": 24,
                       "delivery": "best_effort_at_least_once", "metadata_only": True})
        return result
