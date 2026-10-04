"""Real browser, local HTTP server and a fresh database for every test."""

import os
import socket
import threading
import time
from dataclasses import dataclass

import httpx
import pytest
import uvicorn
from playwright.sync_api import sync_playwright

from everlock.accounts import SESSION_SECONDS
from everlock.app import create_app
from everlock.mailer import Mailer
from everlock.notifications import Notifier

PASSWORD = "Senha de navegador1!"


class UnavailableFaceEngine:
    available = False
    reason = "Modelos ausentes no ambiente isolado de testes."
    model_id = "browser-test-unavailable"

    def read(self, image):
        raise AssertionError("Os testes de interface não devem processar imagens.")


@dataclass
class LocalServer:
    url: str
    app: object
    session_time: list[float]

    def expire_sessions(self):
        with self.app.state.controller.mutex:
            self.session_time[0] += SESSION_SECONDS + 1


@pytest.fixture
def local_server(tmp_path):
    session_time = [time.time()]
    app = create_app(
        tmp_path / "browser.sqlite3",
        session_clock=lambda: session_time[0],
        face_engine=UnavailableFaceEngine(),
        mailer=Mailer(None, "http://127.0.0.1"),
        notifier=Notifier(),
    )
    # Reserving the socket avoids the free-port lookup/startup race in parallel CI.
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        url = f"http://127.0.0.1:{listener.getsockname()[1]}"
        server = uvicorn.Server(uvicorn.Config(app, log_level="warning", access_log=False))
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 15
            while not server.started:
                if not thread.is_alive() or time.monotonic() > deadline:
                    pytest.fail("O servidor local de testes não iniciou.")
                threading.Event().wait(0.01)
            # Seed only synthetic accounts, through the normal HTTP authorization boundary.
            with httpx.Client(base_url=url, trust_env=False) as client:
                assert client.post("/api/auth/setup", json={
                    "username": "admin", "email": "admin@example.invalid", "password": PASSWORD,
                }).status_code == 201
                assert client.post("/api/auth/login", json={
                    "identifier": "admin", "password": PASSWORD,
                }).status_code == 200
                assert client.post("/api/auth/users", json={
                    "username": "visitante", "email": "visitante@example.invalid",
                    "password": PASSWORD, "role": "user",
                }).status_code == 201
            yield LocalServer(url, app, session_time)
        finally:
            server.should_exit = True
            thread.join(timeout=15)
            assert not thread.is_alive(), "O servidor temporário não encerrou."


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as playwright:
        options = {"headless": True}
        channel = os.getenv("EVERLOCK_TEST_BROWSER_CHANNEL")
        if channel:
            options["channel"] = channel
        browser = playwright.chromium.launch(**options)
        yield browser
        browser.close()


@pytest.fixture
def page(browser, local_server):
    context = browser.new_context(base_url=local_server.url, service_workers="block")
    page = context.new_page()
    page.set_default_timeout(7000)
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    yield page
    context.close()
    assert errors == [], f"Erros JavaScript não tratados: {errors}"
