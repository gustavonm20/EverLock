"""Limite de entrada e registros técnicos sem conteúdo das requisições."""

import json
import logging
import time
from datetime import UTC, datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from uuid import uuid4

from starlette.responses import JSONResponse

MAX_REQUEST_BYTES = 16 * 1024 * 1024  # até 7 imagens de 1,5 MB em base64
logger = logging.getLogger("everlock.requests")


def configure_logging(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(folder / "requests.log", maxBytes=1_000_000,
                                  backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False


class RequestBoundary:
    """Limita o corpo antes do parser, inclusive sem Content-Length."""

    def __init__(self, app, max_bytes=MAX_REQUEST_BYTES):
        self.app, self.max_bytes = app, max_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        request_id, started, status = uuid4().hex, time.monotonic(), 500

        async def traced_send(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = message.setdefault("headers", [])
                names = {name for name, _ in headers}
                headers.append((b"x-request-id", request_id.encode()))
                for name, value in ((b"cache-control", b"no-store"),
                                    (b"x-content-type-options", b"nosniff")):
                    if name not in names:
                        headers.append((name, value))
            await send(message)

        async def refuse():
            await JSONResponse({"message": "A solicitação excede o limite de 16 MB."}, 413)(
                scope, receive, traced_send,
            )

        try:
            chunks, size = [], 0
            for key, value in scope.get("headers", []):
                if key == b"content-length":
                    try:
                        if int(value) > self.max_bytes:
                            return await refuse()
                    except ValueError:
                        pass
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                size += len(message.get("body", b""))
                if size > self.max_bytes:
                    return await refuse()
                chunks.append(message.get("body", b""))
                if not message.get("more_body", False):
                    break
            body, delivered = b"".join(chunks), False

            async def buffered_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return await receive()

            await self.app(scope, buffered_receive, traced_send)
        finally:
            # Rota-modelo, sem URL, query, IP, usuário, tokens ou exceção bruta.
            route = getattr(scope.get("route"), "path", "unmatched")
            logger.info(json.dumps({
                "at": datetime.now(UTC).isoformat(), "component": "http",
                "request_id": request_id, "route": route,
                "status": status, "duration_ms": round((time.monotonic() - started) * 1000, 1),
            }))
