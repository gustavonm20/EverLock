"""Rotas do rosto da conta: cadastro, remoção e entrada pelo rosto."""

from fastapi import APIRouter, Path, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from everlock.accounts import SESSION_SECONDS
from everlock.auth_api import COOKIE, authorized
from everlock.faces import FaceError
from everlock.identity_api import decode_image, face_failure

router = APIRouter(prefix="/api/auth")


class FaceEnrollment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: SecretStr = Field(min_length=1)
    consent: bool = Field(strict=True)
    images: list[str] = Field(min_length=3, max_length=5)

    @field_validator("consent")
    @classmethod
    def consent_required(cls, value):
        if value is not True:
            raise ValueError("Sem concordar com o termo, o rosto não pode ser cadastrado.")
        return value


class FaceLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    challenge_id: str = Field(min_length=10, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    front: str = Field(min_length=1)
    turned: list[str] = Field(min_length=1, max_length=6)


@router.get("/face/availability")
def availability(request: Request):
    return request.app.state.face_login.availability()


@router.get("/face/me")
def my_face(request: Request):
    with authorized(request) as user:
        return request.app.state.face_login.info(user["id"])


@router.post("/face/enroll")
def enroll(payload: FaceEnrollment, request: Request):
    with authorized(request) as user:
        images = [decode_image(item) for item in payload.images]
    try:
        code, body = request.app.state.face_login.enroll(
            user, payload.password.get_secret_value(), images, request.client.host,
            authorize=lambda: authorized(request),
        )
    except FaceError as error:
        return face_failure(error)
    return JSONResponse(body, status_code=code)


@router.delete("/face")
def remove_my_face(request: Request):
    with authorized(request) as user:
        request.app.state.accounts.remove_face(user["id"], user["username"])
    return {"message": "Seu rosto foi removido. Você continua entrando com e-mail ou usuário "
                       "e senha."}


@router.delete("/users/{user_id}/face")
def remove_face_of(request: Request, user_id: int = Path(ge=1, le=2**31 - 1)):
    with authorized(request, admin=True) as user:
        request.app.state.accounts.remove_face(user_id, user["username"])
    return {"message": "Rosto da conta removido."}


@router.post("/face/challenge")
def challenge(request: Request):
    return request.app.state.face_login.challenge()


@router.delete("/face/challenge/{challenge_id}")
def cancel_challenge(request: Request, challenge_id: str = Path(
    min_length=10, max_length=64, pattern=r"^[A-Za-z0-9_-]+$",
)):
    request.app.state.face_login.cancel_challenge(challenge_id)
    return {"message": "Desafio encerrado."}


@router.post("/face/login")
def login_with_face(payload: FaceLoginRequest, request: Request):
    front = decode_image(payload.front)
    turned = [decode_image(item) for item in payload.turned]
    try:
        code, body, token = request.app.state.face_login.login(payload.challenge_id, front, turned)
    except FaceError as error:
        return face_failure(error)
    reply = JSONResponse(body, status_code=code)
    if token:
        reply.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True,
                         secure=request.url.scheme == "https", samesite="strict", path="/")
    return reply
