import time
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from threading import RLock

from everlock import __version__
from everlock.domain import Action, Denied, Door, Event, apply_action, expire
from everlock.storage import Storage


class Controller:
    def __init__(self, storage: Storage, clock: Callable[[], float] = time.monotonic):
        self.storage = storage
        self.clock = clock
        self.mutex = RLock()
        self.door = storage.load()
        self._commit(replace(self.door), Event(
            "startup", "Simulador iniciado",
            "Posição virtual recuperada. Nenhuma liberação anterior foi retomada.",
            "system", "info",
        ))

    def _commit(self, candidate: Door, event: Event) -> None:
        candidate.revision = self.door.revision + 1
        candidate.updated_at = datetime.now(UTC).isoformat()
        # Só publica o novo estado em memória após a persistência ter sucesso.
        self.storage.save(candidate, event)
        self.door = candidate

    def tick(self) -> None:
        with self.mutex:
            self._expire_at(self.clock())

    def _expire_at(self, now: float) -> None:
        candidate = replace(self.door)
        event = expire(candidate, now)
        if event:
            self._commit(candidate, event)

    def _status(self) -> dict:
        remaining = max(0.0, (self.door.release_deadline or self.clock()) - self.clock())
        return {
            "mode": "simulation",
            "version": __version__,
            "door": {
                "position": self.door.position,
                "lock": self.door.lock,
                "release_remaining_seconds": round(remaining, 2),
                "secured": self.door.secured,
            },
            "device": {"status": "online"},
            "capabilities": {
                "door": True, "power": False, "connectivity": False,
                "face_recognition": False, "authentication": False,
            },
            "revision": self.door.revision,
            "updated_at": self.door.updated_at,
            "observed_at": datetime.now(UTC).isoformat(),
        }

    def status(self) -> dict:
        with self.mutex:
            self.tick()
            return self._status()

    def action(self, action: Action) -> tuple[int, dict]:
        with self.mutex:
            now = self.clock()
            self._expire_at(now)
            candidate = replace(self.door)
            try:
                event = apply_action(candidate, action, now)
            except Denied as error:
                self._commit(candidate, Event(
                    "action_denied", "Ação recusada", error.message, "lab", "denied",
                ))
                return 409, {
                    "ok": False, "code": error.code, "message": error.message,
                    "state": self._status(),
                }
            self._commit(candidate, event)
            return 200, {"ok": True, "message": event.detail, "state": self._status()}

    def events(self, limit: int) -> list[dict]:
        with self.mutex:
            self.tick()
            return self.storage.events(limit)
