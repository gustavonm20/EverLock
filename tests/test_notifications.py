import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from fakes import FakeFaceEngine
from fastapi.testclient import TestClient

from everlock.app import create_app
from everlock.notifications import (
    DeliveryError,
    Notifier,
    classify,
    sign,
    validate_url,
)

ADMIN = {"username": "admin", "email": "admin@example.com", "password": "Senha de testes1!"}
JSON = {"Content-Type": "application/json"}


class Receiver:
    """Servidor HTTP local que responde com os códigos da fila e guarda o que recebeu."""

    def __init__(self, codes=(200,)):
        self.codes, self.received = list(codes), []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                # Nomes de cabeçalho não diferenciam maiúsculas: guardamos em minúsculas.
                outer.received.append(({k.lower(): v for k, v in self.headers.items()}, body))
                code = outer.codes.pop(0) if len(outer.codes) > 1 else outer.codes[0]
                self.send_response(code)
                if code in {301, 302, 307}:
                    self.send_header("Location", "http://127.0.0.1:9/outro")
                self.end_headers()

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/webhook/everlock"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def receiver():
    servers = []

    def make(codes=(200,)):
        servers.append(Receiver(codes))
        return servers[-1]

    yield make
    for server in servers:
        server.close()


def collecting_notifier(**kwargs):
    sent = []
    notifier = Notifier("http://localhost:5678/webhook/x", sender=sent.append,
                        retry_delays=(0, 0), **kwargs)
    return notifier, sent


def payloads(sent):
    return [json.loads(body) for body in sent]


# --- regras puras ------------------------------------------------------------------------------


def test_classification_and_url_validation():
    assert classify("mains_lost", "info") == "critical"
    assert classify("login_face_denied", "info") == "warning"
    assert classify("recognition_denied", "denied") == "warning"
    assert classify("command_denied", "failed") == "warning"
    assert classify("unlock", "success") == "info" and classify("setup", "info") == "info"
    assert validate_url("http://localhost:5678/webhook/a") == ""
    assert validate_url("https://n8n.exemplo.com/webhook/a") == ""
    bad_urls = ("ftp://x.com/a", "localhost:5678", "http://", "http://user:pass@host/a",
                "javascript:1")
    for bad in bad_urls:
        assert validate_url(bad), bad


def test_signature_is_verifiable_and_depends_on_timestamp_and_body():
    body = b'{"a": 1}'
    first = sign("segredo", "100", body)
    assert first.startswith("sha256=") and len(first) == 7 + 64
    assert first == sign("segredo", "100", body)
    assert first != sign("outro", "100", body)
    assert first != sign("segredo", "101", body)
    assert first != sign("segredo", "100", body + b" ")


def test_notifier_without_valid_url_never_sends():
    for url in ("", "ftp://x/y", "http://user:senha@host/a"):
        notifier = Notifier(url, sender=lambda body: pytest.fail("não deveria enviar"))
        assert not notifier.configured
        assert notifier.publish("mains_lost", "t", "d", force=True) is False
        assert notifier.status()["configured"] is False
    assert "usuário e senha" in Notifier("http://u:p@h/a").status()["reason"]


# --- fila, nível e falhas -----------------------------------------------------------------------


def test_level_filter_payload_and_privacy():
    notifier, sent = collecting_notifier(level="warning")
    assert notifier.publish("unlock", "Liberada", "info", "lab", "success") is False
    assert notifier.publish("recognition_denied", "Recusado", "Identidade #3: fora do horário",
                            "recognition", "denied", "admin") is True
    assert notifier.publish("mains_lost", "Sem energia", "d", "system", "info") is True
    assert notifier.flush()
    first, second = payloads(sent)
    assert first["type"] == "recognition_denied" and first["severity"] == "warning"
    assert first["actor"] == "admin" and first["app"] == "EverLock" and len(first["id"]) == 32
    assert first["detail"] == "Identidade #3: fora do horário" and "occurred_at" in first
    assert second["severity"] == "critical"
    everything, sent_all = collecting_notifier(level="info")
    assert everything.publish("unlock", "x", "y", "lab", "success") and everything.flush()
    assert len(sent_all) == 1
    critical_only, sent_critical = collecting_notifier(level="critical")
    critical_only.publish("recognition_denied", "x", "y", "r", "denied")
    critical_only.publish("mains_lost", "x", "y")
    assert critical_only.flush() and len(sent_critical) == 1
    assert Notifier("http://localhost/a", level="qualquer").level == "warning"


def test_retries_then_succeeds_and_counts():
    calls = []

    def flaky(body):
        calls.append(body)
        if len(calls) < 3:
            raise DeliveryError("HTTP 503", True)

    notifier = Notifier("http://localhost/a", sender=flaky, retry_delays=(0, 0, 0))
    notifier.publish("mains_lost", "t", "d")
    assert notifier.flush()
    status = notifier.status()
    assert len(calls) == 3 and status["sent"] == 1 and status["failed"] == 0
    assert status["last_error"] is None and status["last_ok_at"]


def test_permanent_error_is_not_retried_and_exhausted_retries_fail():
    calls = []

    def refuse(body):
        calls.append(1)
        raise DeliveryError("O destino respondeu HTTP 404.", False)

    notifier = Notifier("http://localhost/a", sender=refuse, retry_delays=(0, 0))
    notifier.publish("mains_lost", "t", "d")
    assert notifier.flush() and len(calls) == 1
    assert notifier.status()["failed"] == 1 and "404" in notifier.status()["last_error"]

    calls.clear()

    def down(body):
        calls.append(1)
        raise DeliveryError("Falha de rede", True)

    other = Notifier("http://localhost/a", sender=down, retry_delays=(0, 0))
    other.publish("mains_lost", "t", "d")
    assert other.flush() and len(calls) == 3 and other.status()["failed"] == 1


def test_publish_never_blocks_and_full_queue_drops_the_oldest():
    gate, started = threading.Event(), threading.Event()
    delivered = []

    def slow(body):
        started.set()
        gate.wait(5)
        delivered.append(json.loads(body)["title"])

    notifier = Notifier("http://localhost/a", sender=slow, queue_size=2, retry_delays=())
    notifier.publish("mains_lost", "primeira", "d")
    assert started.wait(2)  # a primeira está "em voo", presa no sender
    for name in ("segunda", "terceira", "quarta"):  # a fila (2) enche e a mais antiga sai
        assert notifier.publish("mains_lost", name, "d") is True
    assert notifier.status()["dropped"] == 1
    gate.set()
    assert notifier.flush()
    assert delivered == ["primeira", "terceira", "quarta"]


# --- HTTP de verdade ---------------------------------------------------------------------------


def test_http_delivery_is_signed_and_json(receiver):
    server = receiver()
    notifier = Notifier(server.url, "segredo-longo", "info", retry_delays=(0,))
    assert notifier.publish("test", "Teste", "detalhe", force=True) and notifier.flush()
    (headers, body), = server.received
    assert headers["content-type"] == "application/json"
    assert headers["user-agent"].startswith("EverLock/")
    timestamp = headers["x-everlock-timestamp"]
    assert headers["x-everlock-signature"] == sign("segredo-longo", timestamp, body)
    assert json.loads(body)["type"] == "test" and notifier.status()["sent"] == 1


def test_http_without_secret_has_no_signature_and_status_hides_the_path(receiver):
    server = receiver()
    notifier = Notifier(server.url, retry_delays=(0,))
    notifier.publish("mains_lost", "t", "d")
    assert notifier.flush() and "x-everlock-signature" not in server.received[0][0]
    status = notifier.status()
    assert status["destination"].startswith("127.0.0.1:") and "webhook" not in str(status)
    assert status["signed"] is False and status["insecure_transport"] is False
    assert Notifier("http://n8n.exemplo.com/a").status()["insecure_transport"] is True
    assert Notifier("https://n8n.exemplo.com/a").status()["insecure_transport"] is False


def test_http_retries_server_errors_and_refuses_redirects(receiver):
    flaky = receiver([500, 200])
    notifier = Notifier(flaky.url, retry_delays=(0, 0))
    notifier.publish("mains_lost", "t", "d")
    assert notifier.flush() and len(flaky.received) == 2 and notifier.status()["sent"] == 1

    redirecting = receiver([302])
    other = Notifier(redirecting.url, retry_delays=(0, 0))
    other.publish("mains_lost", "t", "d")
    assert other.flush() and len(redirecting.received) == 1  # não seguiu nem repetiu
    assert other.status()["failed"] == 1 and "302" in other.status()["last_error"]


def test_connection_failure_message_does_not_leak_the_address():
    notifier = Notifier("http://127.0.0.1:9/segredo-no-caminho", retry_delays=(0,), timeout=1)
    notifier.publish("mains_lost", "t", "d")
    assert notifier.flush(10)
    error = notifier.status()["last_error"]
    assert "Falha de rede" in error and "segredo-no-caminho" not in error and "9" not in error


# --- integração com o aplicativo -----------------------------------------------------------------


@pytest.fixture
def lab(tmp_path):
    sent = []
    notifier = Notifier("http://localhost:5678/webhook/x", sender=sent.append, retry_delays=(0,))
    app = create_app(tmp_path / "notify.sqlite3", notifier=notifier, face_engine=FakeFaceEngine())
    with TestClient(app, base_url="http://localhost") as client:
        assert client.post("/api/auth/setup", json=ADMIN).status_code == 201
        credentials = {"identifier": "admin", "password": ADMIN["password"]}
        assert client.post("/api/auth/login", json=credentials).status_code == 200
        notifier.flush()
        sent.clear()
        yield client, notifier, sent, app


def test_security_events_reach_the_webhook_but_routine_ones_do_not(lab):
    client, notifier, sent, app = lab
    anonymous = TestClient(app, base_url="http://localhost")
    bad = anonymous.post("/api/auth/login", json={"identifier": "admin", "password": "errada"})
    assert bad.status_code == 401
    assert client.post("/api/actions", json={"action": "key_entry"}).status_code == 200
    assert client.post("/api/actions", json={"action": "close"}).status_code == 200
    notifier.flush()
    kinds = [item["type"] for item in payloads(sent)]
    assert kinds == ["login_denied"]  # abrir e fechar a porta são "info": abaixo do nível
    item = payloads(sent)[0]
    assert item["severity"] == "warning" and item["source"] == "accounts"
    assert "errada" not in json.dumps(item)


def test_denied_recognition_and_power_loss_are_forwarded(lab):
    client, notifier, sent, _ = lab
    unknown = client.post("/api/recognition/simulate", json={"scenario": "no_match"})
    assert unknown.status_code == 409
    outage = client.post("/api/simulation/power", json={"mains_available": False})
    assert outage.status_code == 200
    notifier.flush()
    by_type = {item["type"]: item for item in payloads(sent)}
    assert by_type["recognition_no_match"]["severity"] == "warning"
    assert by_type["recognition_no_match"]["actor"] == "admin"
    assert by_type["mains_lost"]["severity"] == "critical"


def test_status_and_test_endpoints_are_admin_only_and_work(lab):
    client, notifier, sent, app = lab
    status = client.get("/api/notifications/status").json()
    assert status["configured"] and status["destination"] == "localhost:5678"
    queued = client.post("/api/notifications/test", headers=JSON)
    assert queued.status_code == 200 and queued.json()["queued"] is True
    notifier.flush()
    item = payloads(sent)[-1]
    assert item["type"] == "test" and item["actor"] == "admin"
    assert client.get("/api/notifications/status").json()["sent"] >= 0

    person = {"username": "pessoa", "email": "pessoa@example.com", "password": "Ab1@cd"}
    assert client.post("/api/auth/users", json={**person, "role": "user"}).status_code == 201
    anonymous = TestClient(app, base_url="http://localhost")
    for method, path in (("get", "/api/notifications/status"), ("post", "/api/notifications/test")):
        assert getattr(anonymous, method)(path, headers=JSON).status_code == 401
    assert anonymous.post("/api/auth/login", json={"identifier": "pessoa",
                                                   "password": "Ab1@cd"}).status_code == 200
    for method, path in (("get", "/api/notifications/status"), ("post", "/api/notifications/test")):
        assert getattr(anonymous, method)(path, headers=JSON).status_code == 403


def test_app_without_webhook_reports_it_and_sends_nothing(tmp_path):
    app = create_app(tmp_path / "off.sqlite3", notifier=Notifier(""))
    with TestClient(app, base_url="http://localhost") as client:
        assert client.post("/api/auth/setup", json=ADMIN).status_code == 201
        credentials = {"identifier": "admin", "password": ADMIN["password"]}
        assert client.post("/api/auth/login", json=credentials).status_code == 200
        assert client.get("/api/notifications/status").json()["configured"] is False
        result = client.post("/api/notifications/test", headers=JSON).json()
        assert result["queued"] is False and "everlock.env" in result["message"]
