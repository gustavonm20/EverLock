"""Contrato do histórico: cursor estável por ID e exportação limitada explícita."""

from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel

from everlock.auth_api import authorized
from everlock.history import EventFilter, to_csv

router = APIRouter(prefix="/api/events")


class HistoryEvent(BaseModel):
    id: int
    type: str
    title: str
    detail: str
    source: str
    outcome: str
    created_at: str
    simulated_at: float | None
    actor: str | None


class EventPage(BaseModel):
    items: list[HistoryEvent]
    next_cursor: int | None
    has_more: bool


def event_filter(
    outcome: Annotated[str | None, Query(pattern=r"^[a-z_]{1,16}$")] = None,
    source: Annotated[str | None, Query(pattern=r"^[a-z_]{1,32}$")] = None,
    type_: Annotated[str | None, Query(alias="type", pattern=r"^[a-z_]{1,48}$")] = None,
    q: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
    since: Annotated[date | None, Query()] = None,
    until: Annotated[date | None, Query()] = None,
    before_id: Annotated[int | None, Query(ge=1, le=2**63 - 1)] = None,
) -> EventFilter:
    if since and until and since > until:
        raise HTTPException(422, "A data inicial vem depois da data final.")
    return EventFilter(outcome, source, type_, q.strip() if q and q.strip() else None,
                       since, until, before_id)


Filters = Annotated[EventFilter, Depends(event_filter)]


@router.get("", response_model=EventPage)
def events(request: Request, filters: Filters,
           limit: Annotated[int, Query(ge=1, le=100)] = 20):
    with authorized(request, admin=True):
        rows = request.app.state.controller.search_events(limit + 1, filters)
    more = len(rows) > limit
    return {"items": rows[:limit], "has_more": more,
            "next_cursor": rows[limit - 1]["id"] if more else None}


@router.get("/export.csv")
def export_events(request: Request, filters: Filters,
                  limit: Annotated[int, Query(ge=1, le=5000)] = 1000):
    with authorized(request, admin=True):
        rows = request.app.state.controller.search_events(limit + 1, filters)
    more = len(rows) > limit
    name = f"everlock-historico-{datetime.now():%Y%m%d-%H%M%S}.csv"
    return Response(to_csv(rows[:limit]), media_type="text/csv; charset=utf-8", headers={
        "Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store",
        "X-EverLock-Has-More": str(more).lower(),
        "X-EverLock-Next-Cursor": str(rows[limit - 1]["id"]) if more else "",
        "X-EverLock-Row-Count": str(min(len(rows), limit)),
    })
