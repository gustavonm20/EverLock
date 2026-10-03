"""Envio do e-mail de confirmação de cadastro.

As credenciais do servidor de e-mail vêm somente de variáveis de ambiente EVERLOCK_SMTP_*
(ou do arquivo local everlock.env, ignorado pelo Git). Nunca ficam no código nem no
repositório. Sem configuração, o link de confirmação é exibido no terminal do servidor.
"""

import os
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage


class MailError(Exception):
    """Falha ao entregar a mensagem ao servidor de e-mail."""


@dataclass(frozen=True)
class MailSettings:
    host: str
    port: int
    username: str
    password: str = field(repr=False)
    sender: str


class Mailer:
    def __init__(self, settings: MailSettings | None, public_url: str):
        self.settings, self.public_url = settings, public_url.rstrip("/")

    @classmethod
    def from_environment(cls) -> "Mailer":
        env = os.environ
        port = env.get("EVERLOCK_PORT", "8000")
        public_url = env.get("EVERLOCK_PUBLIC_URL", f"http://127.0.0.1:{port}")
        host, user, password = (env.get(f"EVERLOCK_SMTP_{key}", "").strip()
                                for key in ("HOST", "USER", "PASSWORD"))
        if not (host and user and password):
            return cls(None, public_url)
        smtp_port = int(env.get("EVERLOCK_SMTP_PORT", "587"))
        sender = env.get("EVERLOCK_SMTP_FROM", "").strip() or user
        return cls(MailSettings(host, smtp_port, user, password, sender), public_url)

    @property
    def configured(self) -> bool:
        return self.settings is not None

    def confirmation_link(self, token: str) -> str:
        # O token vai no fragmento (#): ele não é enviado ao servidor nem aparece em logs.
        return f"{self.public_url}/#confirmar={token}"

    def send_confirmation(self, to: str, username: str, token: str) -> str:
        """Devolve "email" quando enviou ou "console" quando o envio não está configurado."""
        link = self.confirmation_link(token)
        if self.settings is None:
            print(f"\nEverLock: e-mail não configurado. Link de confirmação de {username}:\n"
                  f"  {link}\n", flush=True)
            return "console"
        message = EmailMessage()
        message["Subject"] = "Confirme seu cadastro no EverLock"
        message["From"], message["To"] = self.settings.sender, to
        message.set_content(
            f"Olá, {username}!\n\n"
            "Recebemos um cadastro no EverLock com este e-mail. Para ativar a conta, abra o "
            f"link abaixo (válido por 24 horas):\n\n{link}\n\n"
            "Se você não fez este cadastro, ignore esta mensagem: nada será ativado.\n"
        )
        self._deliver(message)
        return "email"

    def send_reset(self, to: str, username: str, token: str) -> str:
        """Link de redefinição de senha. Mesmo retorno de `send_confirmation`."""
        link = f"{self.public_url}/#redefinir={token}"
        if self.settings is None:
            print(f"\nEverLock: e-mail não configurado. Link para redefinir a senha de "
                  f"{username}:\n  {link}\n", flush=True)
            return "console"
        message = EmailMessage()
        message["Subject"] = "Redefinir a senha do EverLock"
        message["From"], message["To"] = self.settings.sender, to
        message.set_content(
            f"Olá, {username}!\n\n"
            "Alguém pediu para redefinir a senha desta conta no EverLock. Para escolher uma "
            f"senha nova, abra o link abaixo (válido por 1 hora, uso único):\n\n{link}\n\n"
            "Se não foi você, ignore esta mensagem: a senha atual continua valendo.\n"
        )
        self._deliver(message)
        return "email"

    def _deliver(self, message: EmailMessage) -> None:
        settings = self.settings
        context = ssl.create_default_context()
        try:
            if settings.port == 465:
                server = smtplib.SMTP_SSL(settings.host, settings.port, timeout=15,
                                          context=context)
            else:
                server = smtplib.SMTP(settings.host, settings.port, timeout=15)
            with server:
                if settings.port != 465:
                    server.starttls(context=context)
                server.login(settings.username, settings.password)
                server.send_message(message)
        except (OSError, smtplib.SMTPException) as error:
            raise MailError(type(error).__name__) from error
