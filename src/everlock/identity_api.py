"""Rotas administrativas de identidades e do teste de reconhecimento simulado."""

import base64
import binascii
from typing import Literal

from fastapi import APIRouter, HTTPException, Path, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from everlock.accounts import token_hash
from everlock.auth_api import COOKIE, authorized
from everlock.faces import MAX_IMAGE_BYTES, FaceError
from everlock.identities import (
    ALL_DAYS,
    RETENTION_DEFAULT_DAYS,
    RETENTION_MAX_DAYS,
    RETENTION_MIN_DAYS,
    validate_label,
    validate_schedule,
)

router = APIRouter(prefix="/api")
IdentityId = Path(ge=1, le=2**31 - 1)


class IdentityCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=2, max_length=60)
    retention_days: int = Field(
        default=RETENTION_DEFAULT_DAYS, ge=RETENTION_MIN_DAYS, le=RETENTION_MAX_DAYS, strict=True,
    )
    days: list[int] = Field(default=list(ALL_DAYS), min_length=1, max_length=7)
    start: str = "00:00"
    end: str = "24:00"
    consent: bool = Field(strict=True)
    consent_version: str = Field(min_length=1, max_length=32)

    @field_validator("label")
    @classmethod
    def label_policy(cls, value):
        return validate_label(value)

    @field_validator("consent")
    @classmethod
    def consent_required(cls, value):
        if value is not True:
            raise ValueError(
                "Sem o consentimento confirmado, a identidade não pode ser cadastrada."
            )
        return value

    @model_validator(mode="after")
    def valid_schedule(self):
        validate_schedule(self.days, self.start, self.end)
        return self


class IdentityUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    active: bool | None = Field(default=None, strict=True)
    days: list[int] | None = Field(default=None, max_length=7)
    start: str | None = None
    end: str | None = None

    @model_validator(mode="after")
    def valid_change(self):
        schedule = (self.days, self.start, self.end)
        if any(item is not None for item in schedule):
            if any(item is None for item in schedule):
                raise ValueError("Envie os dias, o início e o fim da janela juntos.")
            validate_schedule(*schedule)
        elif self.active is None:
            raise ValueError("Informe ao menos uma alteração.")
        return self

    @property
    def schedule(self):
        return None if self.days is None else (self.days, self.start, self.end)


class RecognitionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: Literal["match", "no_match"]
    identity_id: int | None = Field(default=None, ge=1, le=2**31 - 1, strict=True)

    @model_validator(mode="after")
    def coherent(self):
        if self.scenario == "match" and self.identity_id is None:
            raise ValueError("Escolha a identidade usada no teste.")
        if self.scenario == "no_match" and self.identity_id is not None:
            raise ValueError("Um rosto desconhecido não usa uma identidade.")
        return self


class FaceEnrollment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    images: list[str] = Field(min_length=3, max_length=5)


class FaceVerification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    challenge_id: str = Field(min_length=10, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    front: str = Field(min_length=1)
    turned: list[str] = Field(min_length=1, max_length=6)


def decode_image(text: str) -> bytes:
    """Aceita base64 puro ou data URL de JPEG/PNG. A imagem nunca vai para o disco."""
    if len(text) > MAX_IMAGE_BYTES * 4 // 3 + 200:
        raise HTTPException(413, "A imagem é grande demais.")
    if text.startswith("data:"):
        text = text.partition(",")[2]
    try:
        image = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError) as error:
        raise HTTPException(422, "A imagem enviada não está em base64 válido.") from error
    if len(image) > MAX_IMAGE_BYTES:
        raise HTTPException(413, "A imagem é grande demais.")
    return image


def face_failure(error: FaceError) -> JSONResponse:
    status = 503 if error.code == "engine_unavailable" else 422
    return JSONResponse({"code": error.code, "message": error.message}, status_code=status)


@router.get("/faces/status")
def faces_status(request: Request):
    with authorized(request, admin=True):
        return request.app.state.recognition.status()


@router.get("/identities/policy")
def policy(request: Request):
    with authorized(request, admin=True):
        return request.app.state.identities.policy()


@router.get("/identities")
def list_identities(request: Request):
    with authorized(request, admin=True):
        return {"items": request.app.state.identities.list()}


@router.get("/identities/events")
def identity_events(request: Request):
    with authorized(request, admin=True):
        return {"items": request.app.state.identities.events()}


@router.post("/identities", status_code=201)
def create_identity(payload: IdentityCreate, request: Request):
    with authorized(request, admin=True) as user:
        return request.app.state.identities.create(
            label=payload.label, retention_days=payload.retention_days, days=payload.days,
            start=payload.start, end=payload.end, consent_version=payload.consent_version,
            actor=user["username"],
        )


@router.patch("/identities/{identity_id}")
def update_identity(payload: IdentityUpdate, request: Request, identity_id: int = IdentityId):
    with authorized(request, admin=True) as user:
        return request.app.state.identities.update(
            identity_id, user["username"], active=payload.active, schedule=payload.schedule,
        )


@router.post("/identities/{identity_id}/enrollment", status_code=201)
def enroll(request: Request, identity_id: int = IdentityId):
    with authorized(request, admin=True) as user:
        return request.app.state.identities.enroll(identity_id, user["username"])


@router.delete("/identities/{identity_id}/enrollment")
def clear_enrollment(request: Request, identity_id: int = IdentityId):
    with authorized(request, admin=True) as user:
        return request.app.state.identities.clear_enrollment(identity_id, user["username"])


@router.post("/identities/{identity_id}/consent/revoke")
def revoke_consent(request: Request, identity_id: int = IdentityId):
    with authorized(request, admin=True) as user:
        return request.app.state.identities.revoke_consent(identity_id, user["username"])


@router.delete("/identities/{identity_id}")
def delete_identity(request: Request, identity_id: int = IdentityId):
    with authorized(request, admin=True) as user:
        request.app.state.identities.delete(identity_id, user["username"])
    return {"message": "Identidade excluída, com cadastro, consentimento e horários."}


@router.post("/identities/{identity_id}/face")
def enroll_face(payload: FaceEnrollment, request: Request, identity_id: int = IdentityId):
    with authorized(request, admin=True) as user:
        request.app.state.identities.decide(identity_id)  # 404 se não existir
        images = [decode_image(item) for item in payload.images]
        try:
            code, body = request.app.state.recognition.enroll_face(
                identity_id, images, user["username"],
            )
        except FaceError as error:
            return face_failure(error)
    return JSONResponse(body, status_code=code)


@router.post("/recognition/verify")
def verify_face(payload: FaceVerification, request: Request):
    with authorized(request, admin=True):
        front = decode_image(payload.front)
        turned = [decode_image(item) for item in payload.turned]
        session_id = token_hash(request.cookies[COOKIE])
    try:
        code, body = request.app.state.recognition.verify(
            payload.challenge_id, front, turned, session_id=session_id,
            authorize=lambda: authorized(request, admin=True),
        )
    except FaceError as error:
        return face_failure(error)
    return JSONResponse(body, status_code=code)


@router.post("/recognition/challenge")
def recognition_challenge(request: Request):
    with authorized(request, admin=True):
        try:
            code, body = request.app.state.recognition.challenge(
                token_hash(request.cookies[COOKIE]),
            )
        except FaceError as error:
            return face_failure(error)
    return JSONResponse(body, status_code=code)


@router.delete("/recognition/challenge/{challenge_id}")
def cancel_recognition_challenge(request: Request, challenge_id: str = Path(
    min_length=10, max_length=64, pattern=r"^[A-Za-z0-9_-]+$",
)):
    with authorized(request, admin=True):
        request.app.state.recognition.cancel_challenge(
            challenge_id, token_hash(request.cookies[COOKIE]),
        )
    return {"message": "Desafio encerrado."}


@router.post("/recognition/simulate")
def simulate_recognition(payload: RecognitionRequest, request: Request):
    with authorized(request, admin=True):
        code, body = request.app.state.recognition.simulate(payload.scenario, payload.identity_id)
    return JSONResponse(body, status_code=code)
