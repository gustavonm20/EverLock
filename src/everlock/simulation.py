"""Uma linha de tempo para a porta e a energia, com eventos em ordem temporal."""

from dataclasses import dataclass, replace
from math import inf

from everlock.domain import Door, Event, expire
from everlock.energy import Power


@dataclass
class Timeline:
    elapsed_seconds: float = 0.0
    speed: int = 1
    paused: bool = False


def power_event(kind: str, now: float) -> Event:
    title, detail = {
        "battery_low": (
            "Bateria virtual baixa", "Carga em 20% ou menos. Perfil econômico ativado.",
        ),
        "battery_critical": (
            "Dispositivo virtual desligado",
            "Carga em 5% ou menos. Liberação encerrada; saída e chave manuais disponíveis.",
        ),
        "battery_empty": (
            "Bateria virtual esgotada", "Reserva em 0 Wh. Restaure a alimentação simulada.",
        ),
        "battery_full": (
            "Bateria virtual carregada", "A carga atingiu a capacidade configurada.",
        ),
    }[kind]
    return Event(kind, title, detail, "system", "info", now)


def advance(door: Door, power: Power, timeline: Timeline, seconds: float) -> list[Event]:
    """Integra por trechos para não pular alertas ao avançar horas de uma vez."""
    events = []
    left = seconds
    while left > 0:
        extra_w = power.config.actuator_extra_w if door.release_deadline is not None else 0
        power_due, kind, target = power.boundary(extra_w)
        release_due = (
            max(0.0, door.release_deadline - timeline.elapsed_seconds)
            if door.release_deadline is not None else inf
        )
        recovery_due = (
            max(0.0, power.recovery_deadline - timeline.elapsed_seconds)
            if power.recovery_deadline is not None else inf
        )
        step = min(left, power_due, release_due, recovery_due)
        power.consume(step, extra_w)
        timeline.elapsed_seconds += step
        left = max(0.0, left - step)
        # Em empate, o desligamento elétrico encerra a liberação antes do prazo.
        if power_due <= step:
            power.stored_wh = target
            if kind == "battery_critical":
                power.device_on = False
                power.recovery_deadline = None
                door.release_deadline = None
            events.append(power_event(kind, timeline.elapsed_seconds))
        if release_due <= step and door.release_deadline is not None:
            # Fixar o instante evita erro de arredondamento na fronteira de três segundos.
            event = expire(door, door.release_deadline)
            if event:
                events.append(Event(
                    event.type, event.title, event.detail, event.source, event.outcome,
                    timeline.elapsed_seconds,
                ))
        if recovery_due <= step and power.recovery_deadline is not None:
            power.device_on = True
            power.recovery_deadline = None
            events.append(Event(
                "device_recovered", "Dispositivo virtual reiniciado",
                "Recuperação concluída sem liberar a trava.", "system", "info",
                timeline.elapsed_seconds,
            ))
    return events


def estimated_runtime(door: Door, power: Power, timeline: Timeline) -> float:
    """Projeção sem futuras liberações; considera o pulso atual e os dois perfis."""
    if power.stored_wh <= power.critical_wh:
        return 0.0
    if not power.device_on and power.recovery_deadline is None:
        return 0.0
    remaining = max(0.0, (door.release_deadline or 0) - timeline.elapsed_seconds)
    if remaining == 0:
        return power.runtime_seconds()
    projected = replace(power, mains_available=False)
    events = advance(replace(door), projected, replace(timeline), remaining)
    for event in events:
        if event.type == "battery_critical":
            return event.simulated_at - timeline.elapsed_seconds
    return remaining + projected.runtime_seconds()
