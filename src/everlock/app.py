import asyncio
import logging
import os
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, model_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from everlock import __version__
from everlock.accounts import Accounts
from everlock.auth_api import COOKIE, authorized
from everlock.auth_api import router as auth_router
from everlock.biometrics import TemplateVault
from everlock.communication import Communication
from everlock.controller import Controller
from everlock.domain import Action
from everlock.energy import PowerConfig
from everlock.face_auth_api import router as face_auth_router
from everlock.face_login import FaceLogin
from everlock.faces import FaceEngine, OpenCVFaceEngine
from everlock.history import EventFilter, to_csv
from everlock.identities import Identities
from everlock.identity_api import router as identity_router
from everlock.mailer import Mailer
from everlock.notifications import Notifier
from everlock.notifications_api import router as notifications_router
from everlock.recognition import Recognition
from everlock.storage import Storage

WEB_DIR = Path(__file__).parent / "web"
PROJECT_DIR = Path(__file__).resolve().parents[2]
logger = logging.getLogger("everlock")


class ActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Action


class CommandRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: UUID
    action: Literal["unlock", "lock"]
    expected_version: UUID
    valid_for_seconds: int = Field(default=10, ge=1, le=30, strict=True)


class NetworkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    internet_available: bool = Field(strict=True)
    lan_available: bool = Field(strict=True)
    delay_seconds: float = Field(default=0, ge=0, le=30, strict=True)


class PowerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mains_available: bool = Field(strict=True)


class ClockRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    paused: bool | None = Field(default=None, strict=True)
    speed: int | None = Field(default=None, strict=True)
    advance_seconds: float | None = Field(default=None, gt=0, le=86400, strict=True)

    @model_validator(mode="after")
    def valid_operation(self):
        if sum(value is not None for value in (self.paused, self.speed, self.advance_seconds)) != 1:
            raise ValueError("Envie apenas uma operação: paused, speed ou advance_seconds.")
        if self.speed is not None and self.speed not in {1, 60, 600}:
            raise ValueError("A velocidade deve ser 1, 60 ou 600.")
        return self


class PowerSetup(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    capacity_wh: float = Field(default=40, ge=1, le=1000, strict=True)
    normal_load_w: float = Field(default=8, ge=0.1, le=100, strict=True)
    economy_load_w: float = Field(default=4, ge=0.1, le=100, strict=True)
    standby_load_w: float = Field(default=0.1, ge=0, le=1, strict=True)
    charge_power_w: float = Field(default=10, ge=0.1, le=100, strict=True)
    efficiency: float = Field(default=0.9, ge=0.5, le=1, strict=True)
    actuator_extra_w: float = Field(default=12, ge=0, le=100, strict=True)
    initial_percent: float = Field(default=100, ge=0, le=100, strict=True)

    @model_validator(mode="after")
    def valid_profile(self):
        PowerConfig(**self.model_dump(exclude={"initial_percent"}))
        return self


def create_app(
    db_path: Path | None = None, clock: Callable[[], float] = time.monotonic,
    session_clock: Callable[[], float] = time.time,
    command_clock: Callable[[], float] = time.monotonic,
    mailer: Mailer | None = None,
    face_engine: FaceEngine | None = None,
    notifier: Notifier | None = None,
) -> FastAPI:
    if db_path is None:
        data_dir = Path(os.getenv("EVERLOCK_DATA_DIR", str(PROJECT_DIR / "data"))).resolve()
        db_path = data_dir / "everlock.sqlite3"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        storage = Storage(db_path)
        try:
            app.state.controller = Controller(storage, clock)
            app.state.accounts = Accounts(storage.connection, app.state.controller.mutex,
                                          session_clock)
            app.state.mailer = mailer or Mailer.from_environment()
            app.state.notifier = notifier or Notifier.from_environment()
            app.state.controller.notifier = app.state.notifier
            app.state.accounts.notifier = app.state.notifier
            app.state.communication = Communication(
                app.state.controller, app.state.accounts, command_clock, session_clock,
            )
            vault = TemplateVault(db_path.parent / "biometria.chave")
            engine = face_engine or OpenCVFaceEngine(db_path.parent / "models")
            app.state.identities = Identities(storage.connection, app.state.controller.mutex,
                                              session_clock, vault)
            app.state.identities.biometrics_enabled = engine.available and vault.available
            app.state.controller.face_recognition_available = (
                app.state.identities.biometrics_enabled
            )
            app.state.recognition = Recognition(app.state.controller, app.state.identities,
                                                engine)
            app.state.face_login = FaceLogin(app.state.accounts, engine, vault, session_clock)
            app.state.identities.notifier = app.state.notifier
            stop = asyncio.Event()

            async def maintain_simulation():
                while not stop.is_set():
                    try:
                        await asyncio.to_thread(app.state.communication.tick)
                    except Exception:
                        logger.exception(
                            "Falha ao atualizar o simulador; uma nova tentativa será feita."
                        )
                    try:
                        await asyncio.wait_for(stop.wait(), timeout=0.1)
                    except TimeoutError:
                        pass

            timer = asyncio.create_task(maintain_simulation())
            try:
                yield
            finally:
                stop.set()
                await timer
                await asyncio.to_thread(app.state.controller.checkpoint)
        finally:
            if "notifier" in app.state._state:
                app.state.notifier.close()
            storage.close()

    app = FastAPI(
        title="EverLock — API do simulador", version=__version__, lifespan=lifespan,
        docs_url=None, redoc_url=None,
    )

    @app.middleware("http")
    async def local_browser_boundary(request: Request, call_next):
        # Origem e JSON complementam a sessão; o servidor continua restrito ao computador.
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            expected = f"{request.url.scheme}://{request.url.netloc}"
            if (origin is not None and origin != expected) or (
                request.headers.get("sec-fetch-site") == "cross-site"
            ):
                return JSONResponse({"message": "Origem da solicitação não permitida."}, 403)
            media_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
            if media_type != "application/json":
                return JSONResponse({"message": "Envie o conteúdo em application/json."}, 415)
        response = await call_next(request)
        response.headers.update({
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            # A câmera só pode ser usada por esta própria página, nunca por conteúdo de terceiros.
            "Permissions-Policy": "camera=(self), microphone=(), geolocation=()",
            "Content-Security-Policy": (
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
                "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
            ),
        })
        return response

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])
    app.include_router(auth_router)
    app.include_router(identity_router)
    app.include_router(face_auth_router)
    app.include_router(notifications_router)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, error: RequestValidationError):
        # O erro padrão pode devolver a entrada original, incluindo senhas.
        return JSONResponse({"detail": [
            {key: item[key] for key in ("loc", "msg", "type")} for item in error.errors()
        ]}, 422)

    @app.get("/api/health")
    def health():
        return {"status": "ok", "app": "EverLock", "version": __version__, "mode": "simulation"}

    @app.get("/api/status")
    def status(request: Request):
        with authorized(request):
            return request.app.state.controller.status()

    def event_filter(
        outcome: Annotated[str | None, Query(pattern=r"^[a-z_]{1,16}$")] = None,
        source: Annotated[str | None, Query(pattern=r"^[a-z_]{1,32}$")] = None,
        type_: Annotated[str | None, Query(alias="type", pattern=r"^[a-z_]{1,48}$")] = None,
        q: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
        since: Annotated[date | None, Query()] = None,
        until: Annotated[date | None, Query()] = None,
    ) -> EventFilter:
        if since and until and since > until:
            raise HTTPException(422, "A data inicial vem depois da data final.")
        return EventFilter(outcome, source, type_, q.strip() if q and q.strip() else None,
                           since, until)

    Filters = Annotated[EventFilter, Depends(event_filter)]

    @app.get("/api/events")
    def events(request: Request, filters: Filters,
               limit: Annotated[int, Query(ge=1, le=100)] = 20):
        with authorized(request, admin=True):
            return {"items": request.app.state.controller.search_events(limit, filters)}

    @app.get("/api/events/export.csv")
    def export_events(request: Request, filters: Filters,
                      limit: Annotated[int, Query(ge=1, le=5000)] = 1000):
        with authorized(request, admin=True):
            rows = request.app.state.controller.search_events(limit, filters)
        name = f"everlock-historico-{datetime.now():%Y%m%d-%H%M%S}.csv"
        return Response(to_csv(rows), media_type="text/csv; charset=utf-8", headers={
            "Content-Disposition": f'attachment; filename="{name}"', "Cache-Control": "no-store",
        })

    @app.get("/api/ups")
    def real_ups(request: Request):
        with authorized(request):
            return {
                "source": "external_equipment", "status": "not_monitored",
                "observation": None, "controls_available": False,
                "message": "O nobreak alimenta o computador. Não há monitoramento pelo EverLock.",
            }

    @app.post("/api/actions")
    def action(payload: ActionRequest, request: Request):
        with authorized(request, admin=payload.action in {"key_entry", "unlock"}):
            code, body = request.app.state.controller.action(payload.action)
        return JSONResponse(body, status_code=code)

    @app.get("/api/communication")
    def communication(request: Request):
        with authorized(request) as user:
            return request.app.state.communication.snapshot(user)

    @app.post("/api/commands")
    def command(payload: CommandRequest, request: Request):
        with authorized(request) as user:
            code, body = request.app.state.communication.submit(
                payload, user, request.cookies[COOKIE],
            )
        return JSONResponse(body, status_code=code)

    @app.get("/api/commands/{command_id}")
    def command_result(command_id: UUID, request: Request):
        with authorized(request) as user:
            return request.app.state.communication.get(str(command_id), user)

    @app.post("/api/simulation/network")
    def configure_network(payload: NetworkRequest, request: Request):
        with authorized(request, admin=True) as user:
            request.app.state.communication.configure(payload)
            return request.app.state.communication.snapshot(user)

    @app.post("/api/simulation/power")
    def power(payload: PowerRequest, request: Request):
        with authorized(request, admin=True):
            code, body = request.app.state.controller.set_power(payload.mains_available)
            request.app.state.communication.tick()
        return JSONResponse(body, status_code=code)

    @app.post("/api/simulation/clock")
    def clock_control(payload: ClockRequest, request: Request):
        with authorized(request, admin=True):
            code, body = request.app.state.controller.control_clock(**payload.model_dump())
            request.app.state.communication.tick()
        return JSONResponse(body, status_code=code)

    @app.post("/api/simulation/power/config")
    def configure_power(payload: PowerSetup, request: Request):
        config = PowerConfig(**payload.model_dump(exclude={"initial_percent"}))
        with authorized(request, admin=True):
            code, body = request.app.state.controller.configure_power(
                config, payload.initial_percent,
            )
            request.app.state.communication.tick()
        return JSONResponse(body, status_code=code)

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(WEB_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
    return app
