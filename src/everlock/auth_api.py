from contextlib import contextmanager
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException, Path, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from everlock.accounts import SESSION_SECONDS, normalize_email, validate_password
from everlock.mailer import MailError

COOKIE = "everlock_session"
router = APIRouter(prefix="/api/auth")


class Login(BaseModel):
    """Entrada por e-mail ou nome de usuário."""

    model_config = ConfigDict(extra="forbid")
    identifier: str = Field(min_length=3, max_length=254)
    password: SecretStr = Field(min_length=1)

    @field_validator("identifier")
    @classmethod
    def normalize(cls, value):
        return value.strip().lower()


class NewCredentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=32, pattern=r"^[a-zA-Z0-9_.-]+$")
    email: str = Field(min_length=3, max_length=254)
    password: SecretStr = Field(min_length=1)

    @field_validator("username")
    @classmethod
    def normalize(cls, value):
        return value.lower()

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        return normalize_email(value)

    @field_validator("password")
    @classmethod
    def password_policy(cls, value):
        validate_password(value.get_secret_value())
        return value


class NewUser(NewCredentials):
    role: Literal["admin", "user"] = "user"


class Registration(NewCredentials):
    confirm_password: SecretStr
    role: Literal["admin", "user"] = "user"
    invite_code: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def passwords_match(self):
        if self.password.get_secret_value() != self.confirm_password.get_secret_value():
            raise ValueError("A confirmação da senha não confere.")
        return self

    @model_validator(mode="after")
    def invite_matches_role(self):
        # Escolher "administrador" é permitido, mas só com o código de convite.
        if self.role == "admin" and not (self.invite_code or "").strip():
            raise ValueError("Conta de administrador exige o código de convite.")
        if self.role == "user" and self.invite_code:
            raise ValueError("O código de convite vale apenas para conta de administrador.")
        return self


class EmailToken(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=20, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class ForgotPassword(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identifier: str = Field(min_length=3, max_length=254)

    @field_validator("identifier")
    @classmethod
    def normalize(cls, value):
        return value.strip().lower()


class PasswordReset(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(min_length=20, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    password: SecretStr = Field(min_length=1)
    confirm_password: SecretStr

    @field_validator("password")
    @classmethod
    def password_policy(cls, value):
        validate_password(value.get_secret_value())
        return value

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
def authorized(request, admin=False, password_session=False):
    controller, accounts = request.app.state.controller, request.app.state.accounts
    # Revalidação e ação compartilham a trava: revogação não disputa com atuação.
    with controller.mutex:
        user = accounts.require(request.cookies.get(COOKIE), admin, password_session)
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
    request.app.state.accounts.setup(payload.username, payload.email,
                                     payload.password.get_secret_value())
    return {"message": "Administrador criado. Entre com sua conta."}


@router.post("/login")
def login(payload: Login, request: Request, response: Response):
    token = request.app.state.accounts.login(
        payload.identifier, payload.password.get_secret_value(), request.client.host,
    )
    response.set_cookie(COOKIE, token, max_age=SESSION_SECONDS, httponly=True,
                        secure=request.url.scheme == "https", samesite="strict", path="/")
    return {"message": "Sessão iniciada."}


def deliver_confirmation(request: Request, email: str, username: str, token: str) -> str:
    """Envia o link fora da trava do controlador: o SMTP pode demorar vários segundos."""
    return request.app.state.mailer.send_confirmation(email, username, token)


@router.post("/register", status_code=201)
def register(payload: Registration, request: Request):
    accounts = request.app.state.accounts
    created = accounts.register(
        payload.username, payload.email, payload.password.get_secret_value(),
        request.client.host, payload.role, payload.invite_code,
    )
    try:
        delivery = deliver_confirmation(request, payload.email, payload.username, created.token)
    except MailError as error:
        accounts.discard_unconfirmed(created.user_id)
        raise HTTPException(
            503, "Não foi possível enviar o e-mail de confirmação. Confira o endereço e "
                 "tente novamente em instantes.",
        ) from error
    return {"delivery": delivery, "message": registration_message(delivery, payload.email)}


def registration_message(delivery: str, email: str) -> str:
    if delivery == "email":
        return (f"Conta criada. Enviamos um e-mail de confirmação para {email}. "
                "Abra o link da mensagem para poder entrar.")
    return ("Conta criada. Este computador ainda não tem e-mail configurado, então o link de "
            "confirmação foi exibido no terminal do servidor.")


@router.post("/confirm-email")
def confirm_email(payload: EmailToken, request: Request):
    request.app.state.accounts.confirm_email(payload.token)
    return {"message": "E-mail confirmado. Agora você já pode entrar."}


@router.post("/resend-confirmation")
def resend_confirmation(payload: Login, request: Request):
    email, username, token = request.app.state.accounts.resend_confirmation(
        payload.identifier, payload.password.get_secret_value(), request.client.host,
    )
    try:
        delivery = deliver_confirmation(request, email, username, token)
    except MailError as error:
        raise HTTPException(503, "Não foi possível enviar o e-mail agora. Tente novamente "
                                 "em instantes.") from error
    return {"delivery": delivery, "message": registration_message(delivery, email)
            .replace("Conta criada. ", "")}


def send_reset_mail(accounts, mailer, email: str, username: str, token: str):
    """Roda depois da resposta: o tempo de envio não revela se a conta existe."""
    try:
        mailer.send_reset(email, username, token)
    except MailError:
        accounts.record("password_reset_mail_failed", username,
                        "Não foi possível enviar o e-mail de redefinição.")


@router.post("/forgot-password", status_code=202)
def forgot_password(payload: ForgotPassword, request: Request, background: BackgroundTasks):
    accounts, mailer = request.app.state.accounts, request.app.state.mailer
    found = accounts.request_password_reset(payload.identifier, request.client.host)
    if found:
        background.add_task(send_reset_mail, accounts, mailer, *found)
    message = ("Se existir uma conta com esse e-mail ou usuário, enviamos um link para "
               "redefinir a senha. O link vale 1 hora.")
    if not mailer.configured:
        message += (" Este computador ainda não tem e-mail configurado: o link aparece no "
                    "terminal do servidor.")
    return {"message": message}


@router.post("/reset-password")
def reset_password(payload: PasswordReset, request: Request):
    request.app.state.accounts.reset_password(payload.token, payload.password.get_secret_value())
    return {"message": "Senha redefinida. Entre com a nova senha."}


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
    with authorized(request, admin=True, password_session=payload.role == "admin") as user:
        request.app.state.accounts.create(
            payload.username, payload.email, payload.password.get_secret_value(),
            payload.role, user["username"],
        )
    return {"message": "Conta criada."}


@router.get("/invites")
def invites(request: Request):
    with authorized(request, admin=True):
        return {"items": request.app.state.accounts.invites()}


@router.post("/invites", status_code=201)
def create_invite(request: Request):
    with authorized(request, admin=True, password_session=True) as user:
        return request.app.state.accounts.create_invite(user["username"])


@router.delete("/invites/{invite_id}")
def revoke_invite(request: Request, invite_id: int = Path(ge=1, le=2**31 - 1)):
    with authorized(request, admin=True) as user:
        request.app.state.accounts.revoke_invite(invite_id, user["username"])
    return {"message": "Convite revogado."}


@router.patch("/users/{user_id}")
def update_user(user_id: int, payload: UserUpdate, request: Request):
    with authorized(request, admin=True, password_session=payload.role == "admin") as user:
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
