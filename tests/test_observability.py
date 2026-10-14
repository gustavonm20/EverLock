import asyncio
import json
import logging

from fastapi.testclient import TestClient

from everlock.app import create_app
from everlock.observability import MAX_REQUEST_BYTES, RequestBoundary


def test_request_id_and_logs_never_contain_input(tmp_path, caplog):
    app = create_app(tmp_path / "logs.sqlite3")
    with TestClient(app, base_url="http://localhost") as client:
        with caplog.at_level(logging.INFO, logger="everlock.requests"):
            response = client.post("/api/auth/login?token=segredo-query", json={
                "identifier": "pessoa-privada", "password": "segredo-senha",
            }, headers={"X-Request-ID": "identificador-controlado-pelo-cliente"})
        request_id = response.headers["x-request-id"]
        assert len(request_id) == 32
        record = json.loads(caplog.records[-1].message)
        assert record["request_id"] == request_id and record["route"] == "/api/auth/login"
        assert record["duration_ms"] >= 0
        assert "segredo" not in caplog.text and "pessoa-privada" not in caplog.text
        large = client.post("/api/auth/login", content=b"{}", headers={
            "content-length": str(MAX_REQUEST_BYTES + 1), "content-type": "application/json",
        })
        assert large.status_code == 413
        assert large.headers["cache-control"] == "no-store"


def test_streamed_body_limit_precedes_application():
    messages = iter([
        {"type": "http.request", "body": b"123456", "more_body": True},
        {"type": "http.request", "body": b"789012", "more_body": False},
    ])
    output = []

    async def receive():
        return next(messages)

    async def send(message):
        output.append(message)

    async def application(*_):
        raise AssertionError("O parser não deve receber um corpo acima do limite.")

    asyncio.run(RequestBoundary(application, max_bytes=10)(
        {"type": "http", "headers": []}, receive, send,
    ))
    assert output[0]["status"] == 413
