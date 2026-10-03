"""Rotas administrativas das notificações."""

from fastapi import APIRouter, Request

from everlock.auth_api import authorized

router = APIRouter(prefix="/api/notifications")


@router.get("/status")
def notification_status(request: Request):
    with authorized(request, admin=True):
        return request.app.state.notifier.status()


@router.post("/test")
def send_test(request: Request):
    with authorized(request, admin=True) as user:
        notifier = request.app.state.notifier
        queued = notifier.publish(
            "test", "Notificação de teste do EverLock",
            f"Teste pedido por {user['username']}. Se você recebeu esta mensagem, a ligação "
            "com o n8n está funcionando.", "notifications", "info", user["username"], force=True,
        )
    return {"queued": queued, "message": (
        "Notificação de teste enviada para a fila. Veja o resultado no status."
        if queued else "Nenhum webhook configurado. Veja everlock.env.example."
    )}
