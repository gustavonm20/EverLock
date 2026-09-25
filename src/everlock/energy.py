"""Modelo didático em Wh. Não estima a autonomia de equipamento real."""

import math
from dataclasses import asdict, dataclass, field

LOW_FRACTION = 0.20
CRITICAL_FRACTION = 0.05


@dataclass(frozen=True)
class PowerConfig:
    capacity_wh: float = 40.0
    normal_load_w: float = 8.0
    economy_load_w: float = 4.0
    standby_load_w: float = 0.1
    charge_power_w: float = 10.0
    efficiency: float = 0.9
    actuator_extra_w: float = 12.0

    def __post_init__(self):
        bounds = {
            "capacity_wh": (1, 1000), "normal_load_w": (0.1, 100),
            "economy_load_w": (0.1, 100), "standby_load_w": (0, 1),
            "charge_power_w": (0.1, 100), "efficiency": (0.5, 1),
            "actuator_extra_w": (0, 100),
        }
        for name, (low, high) in bounds.items():
            value = getattr(self, name)
            if not math.isfinite(value) or not low <= value <= high:
                raise ValueError(f"{name} deve ficar entre {low} e {high}.")
        if self.economy_load_w > self.normal_load_w:
            raise ValueError("O consumo econômico não pode superar o normal.")
        if self.standby_load_w >= self.economy_load_w:
            raise ValueError("O consumo desligado deve ser menor que o econômico.")


@dataclass
class Power:
    config: PowerConfig = field(default_factory=PowerConfig)
    stored_wh: float = 40.0
    mains_available: bool = True
    device_on: bool = True
    recovery_deadline: float | None = None

    @property
    def low_wh(self) -> float:
        return self.config.capacity_wh * LOW_FRACTION

    @property
    def critical_wh(self) -> float:
        return self.config.capacity_wh * CRITICAL_FRACTION

    @property
    def profile(self) -> str:
        if not self.device_on and self.recovery_deadline is None:
            return "off"
        if not self.mains_available and self.stored_wh <= self.low_wh:
            return "economy"
        return "normal"

    @property
    def load_w(self) -> float:
        return {
            "normal": self.config.normal_load_w,
            "economy": self.config.economy_load_w,
            "off": self.config.standby_load_w,
        }[self.profile]

    @property
    def level(self) -> str:
        if self.stored_wh <= 0:
            return "empty"
        if self.stored_wh <= self.critical_wh:
            return "critical"
        return "low" if self.stored_wh <= self.low_wh else "normal"

    @property
    def flow_w(self) -> float:
        return self.battery_flow_w()

    def battery_flow_w(self, extra_load_w: float = 0) -> float:
        """Potência líquida no armazenamento: positiva carrega, negativa consome."""
        if self.mains_available:
            if self.stored_wh >= self.config.capacity_wh:
                return 0.0
            return self.config.charge_power_w * self.config.efficiency
        if self.stored_wh <= 0:
            return 0.0
        return -(self.load_w + extra_load_w) / self.config.efficiency

    def boundary(self, extra_load_w: float = 0) -> tuple[float, str, float]:
        """Segundos até a próxima mudança de perfil, e a energia exata nessa mudança."""
        flow = self.battery_flow_w(extra_load_w)
        if flow > 0:
            target, kind = self.config.capacity_wh, "battery_full"
        elif flow < 0:
            if self.device_on or self.recovery_deadline is not None:
                target, kind = (
                    (self.low_wh, "battery_low") if self.stored_wh > self.low_wh
                    else (self.critical_wh, "battery_critical")
                )
            else:
                target, kind = 0.0, "battery_empty"
        else:
            return math.inf, "", self.stored_wh
        return max(0.0, (target - self.stored_wh) / flow * 3600), kind, target

    def consume(self, seconds: float, extra_load_w: float = 0) -> None:
        self.stored_wh = min(
            self.config.capacity_wh,
            max(0.0, self.stored_wh + self.battery_flow_w(extra_load_w) * seconds / 3600),
        )

    def runtime_seconds(self) -> float:
        """Tempo até 5%, incluindo a troca automática de perfil em 20%."""
        if not self.device_on and self.recovery_deadline is None:
            return 0.0
        normal_wh = max(0.0, self.stored_wh - self.low_wh)
        economy_wh = max(0.0, min(self.stored_wh, self.low_wh) - self.critical_wh)
        return 3600 * self.config.efficiency * (
            normal_wh / self.config.normal_load_w + economy_wh / self.config.economy_load_w
        )

    def snapshot(self, extra_load_w: float = 0) -> dict:
        return {
            "mains_available": self.mains_available,
            "source": "mains" if self.mains_available else (
                "battery" if self.stored_wh > 0 else "none"
            ),
            "profile": self.profile,
            "battery": {
                "stored_wh": round(self.stored_wh, 6),
                "capacity_wh": self.config.capacity_wh,
                "percent": round(self.stored_wh / self.config.capacity_wh * 100, 4),
                "level": self.level,
                "charging": self.flow_w > 0,
                "flow_w": round(self.battery_flow_w(extra_load_w), 6),
                "runtime_seconds": round(self.runtime_seconds(), 3),
            },
            "load_w": self.load_w + extra_load_w,
            "actuator_extra_w_active": extra_load_w,
            "config": asdict(self.config),
            "low_percent": 20, "critical_percent": 5,
        }
