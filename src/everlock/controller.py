import time
from collections.abc import Callable
from dataclasses import asdict, replace
from datetime import UTC, datetime
from threading import RLock

from everlock import __version__
from everlock.domain import Action, Denied, Door, Event, apply_action
from everlock.energy import Power, PowerConfig
from everlock.simulation import Timeline, advance, estimated_runtime, power_event
from everlock.storage import Storage


class Controller:
    def __init__(self, storage: Storage, clock: Callable[[], float] = time.monotonic):
        self.storage = storage
        self.clock = clock
        self.mutex = RLock()
        self.door = storage.load()
        self.power, self.timeline = storage.load_simulation()
        self._last_real = clock()
        self._checkpoint_real = self._last_real
        self._checkpoint_sim = self.timeline.elapsed_seconds
        self._commit(*self._copy(), [Event(
            "startup", "Simulador iniciado",
            "Estado virtual recuperado. Nenhuma liberação anterior foi retomada.",
            "system", "info",
        )])

    def _copy(self) -> tuple[Door, Power, Timeline]:
        return replace(self.door), replace(self.power), replace(self.timeline)

    def _commit(self, door: Door, power: Power, timeline: Timeline, events: list[Event]):
        door.revision = self.door.revision + 1
        door.updated_at = datetime.now(UTC).isoformat()
        stamped = [replace(e, simulated_at=timeline.elapsed_seconds)
                   if e.simulated_at is None else e for e in events]
        # Porta, bateria, relógio e eventos são publicados só depois da transação.
        self.storage.save(door, stamped, power, timeline)
        self.door, self.power, self.timeline = door, power, timeline
        self._checkpoint_real = self._last_real
        self._checkpoint_sim = timeline.elapsed_seconds

    def _sync(self):
        now = max(self._last_real, self.clock())
        seconds = (now - self._last_real) * self.timeline.speed
        if self.timeline.paused:
            seconds = 0.0
        door, power, timeline = self._copy()
        events = advance(door, power, timeline, seconds)
        checkpoint_due = seconds > 0 and (
            now - self._checkpoint_real >= 5 or timeline.elapsed_seconds - self._checkpoint_sim >= 5
        )
        if events or checkpoint_due:
            self._commit(door, power, timeline, events)
            self._checkpoint_real = now
        else:
            self.door, self.power, self.timeline = door, power, timeline
        self._last_real = now

    def tick(self) -> None:
        with self.mutex:
            self._sync()

    def checkpoint(self) -> None:
        with self.mutex:
            self._sync()
            self._commit(*self._copy(), [])

    def _status(self) -> dict:
        remaining = max(0.0, (self.door.release_deadline or 0) - self.timeline.elapsed_seconds)
        extra_w = self.power.config.actuator_extra_w if remaining > 0 else 0
        power = self.power.snapshot(extra_w)
        power["battery"]["runtime_seconds"] = round(
            estimated_runtime(self.door, self.power, self.timeline), 3,
        )
        device_status = "online" if self.power.device_on else (
            "recovering" if self.power.recovery_deadline is not None else "powered_off"
        )
        return {
            "mode": "simulation", "version": __version__,
            "door": {
                "position": self.door.position, "lock": self.door.lock,
                "release_remaining_seconds": round(remaining, 2),
                "secured": self.door.secured,
            },
            "device": {
                "status": device_status,
                "recovery_remaining_seconds": round(max(
                    0, (self.power.recovery_deadline or 0) - self.timeline.elapsed_seconds,
                ), 3),
            },
            "power": power, "simulation": asdict(self.timeline),
            "capabilities": {
                "door": True, "power": True, "connectivity": False,
                "face_recognition": False, "authentication": False,
            },
            "revision": self.door.revision, "updated_at": self.door.updated_at,
            "observed_at": datetime.now(UTC).isoformat(),
        }

    def status(self) -> dict:
        with self.mutex:
            self._sync()
            return self._status()

    def _denied(self, error: Denied) -> tuple[int, dict]:
        self._commit(*self._copy(), [Event(
            "action_denied", "Ação recusada", error.message, "lab", "denied",
        )])
        return 409, {
            "ok": False, "code": error.code, "message": error.message, "state": self._status(),
        }

    def _success(self, message: str) -> tuple[int, dict]:
        return 200, {"ok": True, "message": message, "state": self._status()}

    def action(self, action: Action) -> tuple[int, dict]:
        with self.mutex:
            self._sync()
            door, power, timeline = self._copy()
            try:
                if not power.device_on and action in {"unlock", "end_release", "open"}:
                    raise Denied(
                        "device_recovering" if power.recovery_deadline is not None
                        else "device_powered_off",
                        "Dispositivo virtual indisponível. Saída, chave e fechamento são manuais.",
                    )
                event = apply_action(door, action, timeline.elapsed_seconds)
            except Denied as error:
                return self._denied(error)
            self._commit(door, power, timeline, [event])
            return self._success(event.detail)

    def set_power(self, available: bool) -> tuple[int, dict]:
        with self.mutex:
            self._sync()
            if self.power.mains_available == available:
                return self._denied(Denied(
                    "power_unchanged", "A alimentação já está nesse estado.",
                ))
            door, power, timeline = self._copy()
            power.mains_available = available
            events = [Event(
                "mains_restored" if available else "mains_lost",
                "Alimentação restaurada" if available else "Queda de energia simulada",
                "Rede virtual disponível; recarga iniciada se necessária." if available
                else "Alimentação externa cortada. Operação depende da bateria virtual.",
                "lab", "info",
            )]
            if available:
                if not power.device_on and power.recovery_deadline is None:
                    door.release_deadline = None
                    power.recovery_deadline = timeline.elapsed_seconds + 2
                    events.append(Event(
                        "device_recovering", "Dispositivo virtual recuperando",
                        "Reinicialização em 2 segundos virtuais. Nenhuma liberação será retomada.",
                        "system", "info",
                    ))
            elif power.stored_wh <= power.critical_wh:
                power.device_on = False
                power.recovery_deadline = None
                door.release_deadline = None
                events.append(power_event("battery_critical", timeline.elapsed_seconds))
                if power.stored_wh == 0:
                    events.append(power_event("battery_empty", timeline.elapsed_seconds))
            elif power.stored_wh <= power.low_wh:
                events.append(power_event("battery_low", timeline.elapsed_seconds))
            self._commit(door, power, timeline, events)
            return self._success(events[0].detail)

    def configure_power(self, config: PowerConfig, initial_percent: float) -> tuple[int, dict]:
        with self.mutex:
            self._sync()
            door, _, timeline = self._copy()
            door.release_deadline = None
            timeline.paused, timeline.speed = True, 1
            power = Power(config=config, stored_wh=config.capacity_wh * initial_percent / 100)
            event = Event(
                "power_configured", "Cenário de energia preparado",
                f"Bateria de {config.capacity_wh:g} Wh em {initial_percent:g}%. "
                "Tempo pausado, alimentação ligada e liberação encerrada; posição preservada.",
                "lab", "info",
            )
            self._commit(door, power, timeline, [event])
            return self._success(event.detail)

    def control_clock(
        self, *, paused: bool | None = None, speed: int | None = None,
        advance_seconds: float | None = None,
    ) -> tuple[int, dict]:
        with self.mutex:
            self._sync()
            door, power, timeline = self._copy()
            events = []
            if advance_seconds is not None:
                if not timeline.paused:
                    return self._denied(Denied(
                        "clock_not_paused", "Pause o relógio antes de avançar um intervalo.",
                    ))
                events = advance(door, power, timeline, advance_seconds)
                message = f"Avanço de {advance_seconds:g} segundos virtuais. Relógio pausado."
            elif paused is not None:
                timeline.paused = paused
                message = "Relógio virtual pausado." if paused else "Relógio virtual em andamento."
            else:
                timeline.speed = speed
                message = f"Velocidade alterada para {speed}x; vale para porta e bateria."
            events.append(Event(
                "clock_changed", "Relógio virtual ajustado", message, "lab", "info",
            ))
            self._commit(door, power, timeline, events)
            return self._success(message)

    def events(self, limit: int) -> list[dict]:
        with self.mutex:
            self._sync()
            return self.storage.events(limit)
