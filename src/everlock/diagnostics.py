"""Leitura administrativa dos componentes locais, sem executar ações de teste."""

import sqlite3
from datetime import UTC, datetime

from fastapi import APIRouter, Request

from everlock import __version__
from everlock.auth_api import authorized

router = APIRouter(prefix="/api")

FACE_DETAILS = {
    "dependencies_missing": "As bibliotecas de reconhecimento precisam ser instaladas. "
                            "Consulte o guia de reconhecimento facial.",
    "models_missing": "Os modelos de reconhecimento não foram encontrados. "
                      "Consulte o guia de reconhecimento facial para prepará-los.",
    "models_invalid": "Os modelos não puderam ser carregados. "
                      "Confira os arquivos conforme o guia de reconhecimento facial.",
}


def check(item_id, title, status, summary, detail):
    return {"id": item_id, "title": title, "status": status,
            "summary": summary, "detail": detail}


@router.get("/diagnostics")
def diagnostics(request: Request):
    with authorized(request, admin=True):
        state = request.app.state
        try:
            state.controller.storage.connection.execute("SELECT 1").fetchone()
            database = check(
                "database", "Banco de dados", "ok", "Conexão local respondeu",
                "A consulta de leitura funcionou. A integridade dos dados, a gravação e "
                "a recuperação de backups não foram verificadas por esta consulta.",
            )
        except sqlite3.Error:
            database = check(
                "database", "Banco de dados", "attention", "Consulta indisponível",
                "Não foi possível consultar a conexão local. Consulte os registros do servidor.",
            )

        engine = state.recognition.engine
        engine_ok = bool(engine and engine.available)
        facial = check(
            "face_engine", "Reconhecimento facial", "ok" if engine_ok else "attention",
            "Motor disponível" if engine_ok else "Motor indisponível",
            "O motor está disponível no servidor. Câmera, precisão e giro ainda dependem "
            "de validação real." if engine_ok else FACE_DETAILS.get(
                getattr(engine, "reason_code", ""),
                "O motor facial não está disponível. Consulte o guia de reconhecimento facial.",
            ),
        )
        vault_ok = bool(state.face_login.vault and state.face_login.vault.available)
        protection = check(
            "biometric_storage", "Proteção dos cadastros faciais",
            "info" if vault_ok else "attention",
            "Biblioteca disponível" if vault_ok else "Biblioteca indisponível",
            "A biblioteca de cifra está disponível. Esta consulta não abre a chave nem "
            "verifica os cadastros existentes." if vault_ok else
            "O cadastro facial precisa da biblioteca de cifra. Consulte o guia de instalação.",
        )
        mail = check(
            "email", "E-mail", "info",
            "Configurado; envio não verificado" if state.mailer.configured else
            "Envio por e-mail não configurado",
            "Esta consulta não envia mensagens nem testa o servidor de e-mail." if
            state.mailer.configured else
            "Os links de confirmação e recuperação aparecem no terminal do servidor.",
        )
        notifier = state.notifier
        with notifier.lock:
            if notifier.reason:
                notification = check(
                    "notifications", "Notificações opcionais", "attention",
                    "Configuração inválida", "Revise a configuração local conforme o guia "
                    "de notificações. Nenhum envio é realizado por esta consulta.",
                )
            elif not notifier.configured:
                notification = check(
                    "notifications", "Notificações opcionais", "info", "Não configuradas",
                    "O EverLock continua funcionando sem as notificações externas.",
                )
            elif notifier.last_error:
                notification = check(
                    "notifications", "Notificações opcionais", "attention",
                    "O último envio falhou", "Consulte o painel de notificações em Atividade. "
                    "Esta consulta não reenvia mensagens.",
                )
            else:
                notification = check(
                    "notifications", "Notificações opcionais", "info",
                    "Configuradas", "A configuração está presente; esta consulta não confirma "
                    "recebimento ou processamento pelo serviço externo.",
                )

        return {
            "version": __version__, "mode": "simulation",
            "checked_at": datetime.now(UTC).isoformat(),
            "checks": [check(
                "application", "Aplicação local", "ok", "Servidor respondeu",
                "O servidor respondeu a esta consulta autenticada. Porta, trava e energia "
                "são simuladas; o nobreak externo não é monitorado.",
            ), database, facial, protection, mail, notification],
        }
