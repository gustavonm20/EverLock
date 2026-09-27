from contextlib import contextmanager
from typing import Literal

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from everlock.accounts import SESSION_SECONDS, validate_password

COOKIE = "everlock_session"
router = APIRouter(prefix="/api/auth")


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: SecretStr = Field(min_length=1)

    @field_validator("username")
    @classmethod
    def normalize(cls, value):
        return value.lower()


class NewCredentials(Credentials):
    @field_validator("password")
    @classmethod
    def password_policy(cls, value):
        validate_password(value.get_secret_value())
        return value


class NewUser(NewCredentials):
    role: Literal["admin", "user"] = "user"


class Registration(NewCredentials):
    confirm_password: SecretStr

    @model_validator(mode="after")
    def passwords_match(self):
        if self.password.get_secret_value() != self.confirm_password.get_secret_value():
            raise ValueError("A confirmação da senha não confere.")
        return self


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["admin", "user"]
    active: bool = Field(strict=True)


class PasswordUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: SecretStr = Field(min_length=1)
    new_password: SecretStr

    @field_validator("new_password")
    @classmethod
    def password_policy(cls, value):
        validate_password(value.get_secret_value())
        return value


@contextmanager
def authorized(request, admin=False):
    controller, accounts = request.app.state.controller, request.app.state.accounts
    # Revalidação e ação compartilham a trava: revogação não disputa com atuação.
    with controller.mutex:
        user = accounts.require(request.cookies.get(COOKIE), admin)
        controller.actor = user["username"]
        try:
            yield user
        finally:
            controller.actor = None


@router.get("/session")
def session(request: Request):
    with request.app.state.controller.mutex:
        accounts = request.app.state.accounts
        return {"setup_required": accounts.needs_setup(),
                "user": accounts.current(request.cookies.get(COOKIE))}


@router.post("/setup", status_code=201)
def setup(payload: NewCredentials, request: Request):
    request.app.state.accounts.setup(payload.username, payload.password.get_secret_value())
    return {"message": "Administrador criado. Entre com sua conta."}


@router.post("/login")
def login(payload: Credentials, request: Request, response: Response):
    token = request.app.state.accounts.login(
        payload.username, payload.password.get_secret_value(), request.client.host,
    )
    response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True,
                        secure=request.url.scheme == "https", samesite="strict", path="/")
    return {"message": "Sessão iniciada."}


@router.post("/register", status_code=201)
def register(payload: Registration, request: Request):
    request.app.state.accounts.register(
        payload.username, payload.password.get_secret_value(), request.client.host,
    )
    return {"message": "Cadastro enviado. Aguarde a aprovação de um administrador para entrar."}


@router.post("/logout")
def logout(request: Request, response: Response):
    with request.app.state.controller.mutex:
        request.app.state.accounts.logout(request.cookies.get(COOKIE))
    response.delete_cookie(COOKIE, path="/", httponly=True, samesite="strict")
    return {"message": "Sessão encerrada."}


@router.get("/users")
def users(request: Request):
    with authorized(request, admin=True):
        return {"items": request.app.state.accounts.users()}


@router.post("/users", status_code=201)
def create_user(payload: NewUser, request: Request):
    with authorized(request, admin=True) as user:
        request.app.state.accounts.create(payload.username, payload.password.get_secret_value(),
                                          payload.role, user["username"])
    return {"message": "Conta criada."}


@router.patch("/users/{user_id}")
def update_user(user_id: int, payload: UserUpdate, request: Request):
    with authorized(request, admin=True) as user:
        request.app.state.accounts.update(user_id, payload.role, payload.active, user["username"])
    return {"message": "Conta atualizada; as sessões dela foram encerradas."}


@router.post("/password")
def change_password(payload: PasswordUpdate, request: Request, response: Response):
    with authorized(request) as user:
        request.app.state.accounts.change_password(
            user, payload.current_password.get_secret_value(),
            payload.new_password.get_secret_value(),
        )
    response.delete_cookie(COOKIE, path="/", httponly=True, samesite="strict")
    return {"message": "Senha alterada. Entre novamente."}


@router.get("/events")
def account_events(request: Request):
    with authorized(request, admin=True):
        return {"items": request.app.state.accounts.events()}
