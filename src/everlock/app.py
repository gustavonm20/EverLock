import asyncio
import logging
import os
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, model_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from everlock import __version__
from everlock.controller import Controller
from everlock.domain import Action
from everlock.energy import PowerConfig
from everlock.storage import Storage

WEB_DIR = Path(__file__).parent / "web"
PROJECT_DIR = Path(__file__).resolve().parents[2]
logger = logging.getLogger("everlock")


class ActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Action


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
) -> FastAPI:
    if db_path is None:
        data_dir = Path(os.getenv("EVERLOCK_DATA_DIR", str(PROJECT_DIR / "data"))).resolve()
        db_path = data_dir / "everlock.sqlite3"

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        storage = Storage(db_path)
        try:
            app.state.controller = Controller(storage, clock)
            stop = asyncio.Event()

            async def maintain_simulation():
                while not stop.is_set():
                    try:
                        await asyncio.to_thread(app.state.controller.tick)
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
            storage.close()

    app = FastAPI(
        title="EverLock — API do simulador", version=__version__, lifespan=lifespan,
        docs_url=None, redoc_url=None,
    )

    @app.middleware("http")
    async def local_browser_boundary(request: Request, call_next):
        # Defesa para o laboratório local. Não substitui autenticação em versões futuras.
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
            "Content-Security-Policy": (
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
                "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
            ),
        })
        return response

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"])

    @app.get("/api/health")
    def health():
        return {"status": "ok", "app": "EverLock", "version": __version__, "mode": "simulation"}

    @app.get("/api/status")
    def status(request: Request):
        return request.app.state.controller.status()

    @app.get("/api/events")
    def events(request: Request, limit: int = Query(default=20, ge=1, le=100)):
        return {"items": request.app.state.controller.events(limit)}

    @app.post("/api/actions")
    def action(payload: ActionRequest, request: Request):
        code, body = request.app.state.controller.action(payload.action)
        return JSONResponse(body, status_code=code)

    @app.post("/api/simulation/power")
    def power(payload: PowerRequest, request: Request):
        code, body = request.app.state.controller.set_power(payload.mains_available)
        return JSONResponse(body, status_code=code)

    @app.post("/api/simulation/clock")
    def clock_control(payload: ClockRequest, request: Request):
        code, body = request.app.state.controller.control_clock(**payload.model_dump())
        return JSONResponse(body, status_code=code)

    @app.post("/api/simulation/power/config")
    def configure_power(payload: PowerSetup, request: Request):
        config = PowerConfig(**payload.model_dump(exclude={"initial_percent"}))
        code, body = request.app.state.controller.configure_power(config, payload.initial_percent)
        return JSONResponse(body, status_code=code)

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(WEB_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
    return app
