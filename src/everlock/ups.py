"""Contrato de leitura do nobreak real. Nenhum driver foi escolhido ou conectado."""

import time
from datetime import datetime
from threading import RLock

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UPSObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    observed_at: datetime
    model: str | None = Field(default=None, max_length=120)
    external_power: bool | None = Field(default=None, strict=True)
    battery_percent: float | None = Field(default=None, ge=0, le=100)
    runtime_seconds: float | None = Field(default=None, ge=0)

    @field_validator("observed_at")
    @classmethod
    def timezone_required(cls, value):
        if value.utcoffset() is None:
            raise ValueError("A leitura precisa informar fuso horário.")
        return value


class UPSMonitor:
    def __init__(self, clock=time.time, stale_seconds=15):
        self.clock, self.stale_seconds = clock, stale_seconds
        self.configured = False
        self.reading = None
        self.failed = False
        self.mutex = RLock()

    def receive(self, reading: UPSObservation):
        # Somente o futuro adaptador interno poderá alimentar este contrato.
        # Não há rota HTTP para injetar números e apresentá-los como medição real.
        with self.mutex:
            if reading.observed_at.timestamp() > self.clock() + 1:
                raise ValueError("Leitura com horário futuro.")
            if self.reading and reading.observed_at < self.reading.observed_at:
                return
            self.configured, self.failed, self.reading = True, False, reading

    def unavailable(self):
        with self.mutex:
            self.configured, self.failed = True, True

    def snapshot(self):
        with self.mutex:
            age = (max(0, self.clock() - self.reading.observed_at.timestamp())
                   if self.reading else None)
            status = "not_configured" if not self.configured else (
                "unavailable" if self.failed or self.reading is None else
                "stale" if age >= self.stale_seconds else "available"
            )
            return {
                "source": "real_ups", "status": status,
                "telemetry_connected": status == "available", "age_seconds": age,
                "stale_after_seconds": self.stale_seconds,
                "observation": self.reading.model_dump(mode="json") if self.reading else None,
                "controls_available": False,
            }
