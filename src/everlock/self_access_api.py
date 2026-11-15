"""Acesso pela porta com o próprio rosto, na sessão da própria pessoa.

O administrador cria a identidade (horário, retenção, ativação) e a vincula a uma conta. A
pessoa dona da conta lê o termo, registra o próprio aceite, captura o próprio rosto, remove o
cadastro ou revoga o consentimento. A decisão de liberar continua no servidor: o reconhecimento
aponta a identidade e `identities.evaluate()` confere as regras antes da atuação.

O aceite registrado aqui fica marcado como feito na sessão da conta vinculada. Isso é mais forte
que a declaração presencial na sessão do administrador, mas não comprova quem estava diante do
teclado: quem tem a sessão e a senha da conta consegue registrar o aceite.
"""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from everlock.auth_api import authorized
from everlock.faces import FaceError
from everlock.identity_api import SubjectConsent, decode_image, face_failure

router = APIRouter(prefix="/api/me/door-access")


class SelfFaceEnrollment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: SecretStr = Field(min_length=1)
    images: list[str] = Field(min_length=3, max_length=5)


def linked_identity(request: Request, user) -> int:
    identity_id = request.app.state.identities.linked_to(user["id"])
    if identity_id is None:
        raise HTTPException(404, "Nenhuma identidade da porta está vinculada à sua conta. "
                                 "Peça a um administrador para criar e vincular uma.")
    return identity_id


def my_view(request: Request, user) -> dict:
    """Visão completa da própria pessoa: identidade vinculada, termo e estado do motor."""
    state = request.app.state
    recognition = state.recognition.status()
    return {
        **state.identities.self_view(user["id"]),
        "engine": {"available": recognition["available"], "reason": recognition["reason"],
                   "kind": recognition["engine_kind"]},
    }


@router.get("")
def my_door_access(request: Request):
    with authorized(request) as user:
        return my_view(request, user)


@router.post("/consent")
def confirm_my_consent(payload: SubjectConsent, request: Request):
    with authorized(request) as user:
        identity_id = linked_identity(request, user)
        request.app.state.identities.confirm_subject_consent(
            identity_id, payload.version, user["username"], self_service=True,
        )
        return my_view(request, user)


@router.post("/face")
def enroll_my_face(payload: SelfFaceEnrollment, request: Request):
    with authorized(request) as user:
        identity_id = linked_identity(request, user)
        request.app.state.identities.require_subject_consent(identity_id)
        images = [decode_image(item) for item in payload.images]
        request.app.state.accounts.confirm_password(
            user["username"], payload.password.get_secret_value(), request.client.host,
        )
        try:
            code, body = request.app.state.recognition.enroll_face(
                identity_id, images, user["username"],
            )
        except FaceError as error:
            return face_failure(error)
        if code == 201:
            body = {"message": body["message"],
                    "access": my_view(request, user)}
    return JSONResponse(body, status_code=code)


@router.delete("/face")
def remove_my_face(request: Request):
    with authorized(request) as user:
        identity_id = linked_identity(request, user)
        request.app.state.identities.clear_enrollment(identity_id, user["username"])
        return {"message": "Seu cadastro facial da porta foi apagado. A trava não será liberada "
                           "pelo seu rosto até um novo cadastro.",
                "access": my_view(request, user)}


@router.post("/revoke")
def revoke_my_consent(request: Request):
    with authorized(request) as user:
        identity_id = linked_identity(request, user)
        request.app.state.identities.revoke_consent(identity_id, user["username"])
        return {"message": "Consentimento revogado. Os vetores faciais foram apagados e o "
                           "reconhecimento não libera mais a trava para esta identidade.",
                "access": my_view(request, user)}
