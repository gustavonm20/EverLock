"""Regras puras da porta virtual, independentes da interface e do banco."""

from dataclasses import dataclass
from typing import Literal

Action = Literal["unlock", "end_release", "open", "close", "exit", "key_entry"]
RELEASE_SECONDS = 3.0


@dataclass
class Door:
    position: Literal["open", "closed"] = "closed"
    release_deadline: float | None = None
    revision: int = 0
    updated_at: str = ""

    @property
    def lock(self) -> str:
        if self.release_deadline is not None:
            return "released"
        return "engaged" if self.position == "closed" else "pending_close"

    @property
    def secured(self) -> bool:
        return self.position == "closed" and self.lock == "engaged"


@dataclass(frozen=True)
class Event:
    type: str
    title: str
    detail: str
    source: str = "lab"
    outcome: str = "success"


class Denied(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def expire(door: Door, now: float) -> Event | None:
    if door.release_deadline is None or now < door.release_deadline:
        return None
    door.release_deadline = None
    detail = (
        "O prazo terminou. A porta virtual está fechada e a trava está engatada."
        if door.position == "closed"
        else "O prazo terminou. A trava aguarda o fechamento da porta virtual."
    )
    return Event("release_expired", "Liberação encerrada", detail, "system")


def apply_action(door: Door, action: Action, now: float) -> Event:
    """O controlador expira prazos antes de aplicar uma nova ação."""
    if action == "unlock":
        if door.release_deadline is not None:
            raise Denied("already_released", "A liberação já está ativa; o prazo não foi ampliado.")
        door.release_deadline = now + RELEASE_SECONDS
        return Event("unlock", "Acesso liberado", "Trava virtual liberada por 3 segundos.")
    if action == "end_release":
        if door.release_deadline is None:
            raise Denied("not_released", "Não há uma liberação ativa para encerrar.")
        door.release_deadline = None
        detail = (
            "A trava virtual engatou com a porta fechada."
            if door.position == "closed"
            else "A porta continua aberta; a trava aguarda o fechamento."
        )
        return Event("end_release", "Liberação encerrada pelo painel", detail)
    if action in ("open", "exit", "key_entry"):
        if door.position == "open":
            raise Denied("already_open", "A porta virtual já está aberta.")
        if action == "open" and (
            door.release_deadline is None or now >= door.release_deadline
        ):
            raise Denied("door_locked", "Acesso negado: a trava virtual está engatada.")
        door.position = "open"
        if action == "exit":
            door.release_deadline = None
            return Event(
                "exit", "Saída pelo interior", "Saída manual simulada permitida.", "manual",
            )
        if action == "key_entry":
            door.release_deadline = None
            return Event(
                "key_entry", "Entrada com chave", "Acesso com chave manual simulado.", "manual",
            )
        return Event("open", "Porta aberta", "O sensor virtual confirmou a abertura.")
    if action == "close":
        if door.position == "closed":
            raise Denied("already_closed", "A porta virtual já está fechada.")
        door.position = "closed"
        detail = (
            "O sensor virtual confirmou o fechamento. A liberação ainda está ativa."
            if door.release_deadline is not None
            else "O sensor virtual confirmou o fechamento e a trava engatada."
        )
        return Event("close", "Porta fechada", detail)
    raise ValueError(f"Ação desconhecida: {action}")
