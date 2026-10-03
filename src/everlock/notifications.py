"""Notificações de eventos por webhook (pensado para o n8n), opcionais e em segundo plano.

Nada é enviado sem EVERLOCK_WEBHOOK_URL. O envio nunca atrasa a porta nem as contas: o evento
entra numa fila e uma thread própria entrega, com tentativas e prazo curto. A mensagem leva só
o texto do evento (que cita número de identidade, nunca apelido; contas citam o usuário) e pode
ser assinada com HMAC-SHA256 para o receptor conferir a origem.
"""

import hashlib
import hmac
import ipaddress
import json
import os
import queue
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import uuid4

from everlock import __version__

LEVELS = {"info": 0, "warning": 1, "critical": 2}
CRITICAL_TYPES = {"mains_lost", "device_powered_off", "battery_depleted"}
WARNING_TYPES = {
    "login_denied", "login_face_denied", "login_unconfirmed", "permission_denied",
    "invite_rejected", "device_recovering", "command_denied", "action_denied",
}
RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


class DeliveryError(Exception):
    """Falha ao entregar. `retry` diz se vale tentar de novo."""

    def __init__(self, message: str, retry: bool):
        super().__init__(message)
        self.retry = retry


def classify(kind: str, outcome: str = "info") -> str:
    if kind in CRITICAL_TYPES:
        return "critical"
    if kind in WARNING_TYPES or outcome in {"denied", "failed"}:
        return "warning"
    return "info"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None  # redirecionar poderia levar o envio a outro destino


def sign(secret: str, timestamp: str, body: bytes) -> str:
    mac = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256)
    return "sha256=" + mac.hexdigest()


def validate_url(url: str) -> str:
    """Devolve "" se a URL serve ou o motivo de não servir."""
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"} or not parts.hostname:
        return "A URL do webhook deve começar com http:// ou https://."
    if parts.username or parts.password:
        return "A URL do webhook não pode conter usuário e senha."
    return ""


def _is_local(host: str) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_private
    except ValueError:
        return False


class Notifier:
    def __init__(self, url: str = "", secret: str = "", level: str = "warning", *,
                 sender=None, retry_delays=(1.0, 5.0, 30.0), queue_size: int = 100,
                 timeout: float = 5.0):
        self.url = url.strip()
        self.secret = secret
        self.level = level if level in LEVELS else "warning"
        self.retry_delays, self.timeout = tuple(retry_delays), timeout
        self.reason = validate_url(self.url) if self.url else ""
        self.sender = sender or self._http_send
        self.queue: queue.Queue = queue.Queue(maxsize=queue_size)
        self.lock = threading.Lock()
        self.sent = self.failed = self.dropped = self.pending = 0
        self.last_ok_at = self.last_error = None
        self._worker = None
        self._opener = urllib.request.build_opener(_NoRedirect)

    @classmethod
    def from_environment(cls) -> "Notifier":
        env = os.environ
        return cls(env.get("EVERLOCK_WEBHOOK_URL", ""), env.get("EVERLOCK_WEBHOOK_SECRET", ""),
                   env.get("EVERLOCK_WEBHOOK_LEVEL", "warning").strip().lower())

    @property
    def configured(self) -> bool:
        return bool(self.url) and not self.reason

    # --- publicação ---------------------------------------------------------------------

    def publish(self, kind, title, detail, source="lab", outcome="info", actor=None, *,
                force=False) -> bool:
        """Coloca o evento na fila, se couber no nível configurado. Nunca bloqueia nem falha."""
        if not self.configured:
            return False
        severity = classify(kind, outcome)
        if not force and LEVELS[severity] < LEVELS[self.level]:
            return False
        payload = {
            "app": "EverLock", "version": __version__, "id": uuid4().hex, "type": kind,
            "severity": severity, "title": title, "detail": detail, "source": source,
            "outcome": outcome, "actor": actor,
            "occurred_at": datetime.now(UTC).isoformat(),
        }
        body = json.dumps(payload, ensure_ascii=False).encode()
        with self.lock:
            while True:
                try:
                    self.queue.put_nowait(body)
                    self.pending += 1
                    break
                except queue.Full:
                    try:  # fila cheia (destino fora do ar): descarta o mais antigo
                        self.queue.get_nowait()
                        self.dropped += 1
                        self.pending -= 1
                    except queue.Empty:
                        continue
            if self._worker is None:
                self._worker = threading.Thread(target=self._run, name="everlock-webhook",
                                                daemon=True)
                self._worker.start()
        return True

    def publish_event(self, event) -> bool:
        return self.publish(event.type, event.title, event.detail, event.source, event.outcome,
                            event.actor)

    # --- entrega ------------------------------------------------------------------------

    def _run(self):
        while True:
            body = self.queue.get()
            if body is None:
                return
            try:
                self._deliver(body)
            finally:
                with self.lock:
                    self.pending -= 1

    def _deliver(self, body: bytes):
        attempts = len(self.retry_delays) + 1
        for attempt in range(attempts):
            try:
                self.sender(body)
            except DeliveryError as error:
                last = attempt == attempts - 1
                if not error.retry or last:
                    with self.lock:
                        self.failed += 1
                        self.last_error = str(error)
                    return
                time.sleep(self.retry_delays[attempt])
            else:
                with self.lock:
                    self.sent += 1
                    self.last_ok_at = datetime.now(UTC).isoformat()
                    self.last_error = None
                return

    def _http_send(self, body: bytes):
        timestamp = str(int(time.time()))
        headers = {"Content-Type": "application/json", "User-Agent": f"EverLock/{__version__}",
                   "X-EverLock-Timestamp": timestamp}
        if self.secret:
            headers["X-EverLock-Signature"] = sign(self.secret, timestamp, body)
        request = urllib.request.Request(self.url, data=body, headers=headers, method="POST")
        try:
            with self._opener.open(request, timeout=self.timeout):
                return
        except urllib.error.HTTPError as error:
            raise DeliveryError(f"O destino respondeu HTTP {error.code}.",
                                error.code in RETRYABLE_STATUS) from error
        except (urllib.error.URLError, OSError, ValueError) as error:
            # Só o tipo do erro: a mensagem do sistema pode conter o endereço do destino.
            raise DeliveryError(f"Falha de rede ao enviar ({type(error).__name__}).",
                                True) from error

    # --- apoio --------------------------------------------------------------------------

    def flush(self, timeout: float = 5.0) -> bool:
        """Espera a fila esvaziar (testes e encerramento). Devolve False se estourou o prazo."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            with self.lock:
                if self.pending <= 0:
                    return True
            time.sleep(0.01)
        return False

    def close(self):
        if self._worker is not None:
            self.flush(2.0)
            try:
                self.queue.put_nowait(None)
            except queue.Full:
                pass
            self._worker = None

    def status(self) -> dict:
        parts = urlsplit(self.url) if self.configured else None
        host = None
        if parts:
            host = parts.hostname + (f":{parts.port}" if parts.port else "")
        with self.lock:
            return {
                "configured": self.configured, "reason": self.reason, "destination": host,
                "level": self.level, "signed": bool(self.secret),
                "insecure_transport": bool(parts and parts.scheme == "http"
                                           and not _is_local(parts.hostname)),
                "queued": max(self.pending, 0), "sent": self.sent, "failed": self.failed,
                "dropped": self.dropped, "last_ok_at": self.last_ok_at,
                "last_error": self.last_error,
            }
