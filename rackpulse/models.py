from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class DeviceStatus(str, Enum):
    OK = "ok"
    UNREACHABLE = "unreachable"
    STALE = "stale"
    ERROR = "error"


class RackStatus(str, Enum):
    OK = "ok"
    WARNING = "warning"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


@dataclass
class MetricReading:
    power_watts: float | None = None
    energy_kwh: float | None = None
    cpu_percent: float | None = None
    ram_percent: float | None = None
    temperature_c: float | None = None
    gpu_power_watts: float | None = None
    gpu_util_percent: float | None = None
    volts: float | None = None
    amps: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class DeviceReading:
    name: str
    device_type: str
    host: str
    rack: str
    status: DeviceStatus
    metrics: MetricReading = field(default_factory=MetricReading)
    last_poll: datetime | None = None
    error: str | None = None
    vms: list[VmReading] = field(default_factory=list)

    @property
    def power_watts(self) -> float | None:
        if self.metrics.power_watts is not None:
            return self.metrics.power_watts
        if self.metrics.gpu_power_watts is not None:
            return self.metrics.gpu_power_watts
        return None


@dataclass
class VmReading:
    vmid: int
    name: str
    host: str
    cpu_percent: float | None = None
    ram_percent: float | None = None
    status: str | None = None


@dataclass
class RackReading:
    name: str
    location: str
    power_watts: float | None
    power_cap_watts: float | None
    status: RackStatus
    devices: list[DeviceReading] = field(default_factory=list)
    warning_watts: float | None = None
    critical_watts: float | None = None

    @property
    def power_kw(self) -> float | None:
        if self.power_watts is None:
            return None
        return round(self.power_watts / 1000, 2)


@dataclass
class PollSnapshot:
    racks: list[RackReading] = field(default_factory=list)
    last_poll: datetime | None = None
    poll_interval_seconds: int = 60

    @property
    def total_power_watts(self) -> float | None:
        values = [r.power_watts for r in self.racks if r.power_watts is not None]
        if not values:
            return None
        return round(sum(values), 1)

    @property
    def total_power_kw(self) -> float | None:
        total = self.total_power_watts
        if total is None:
            return None
        return round(total / 1000, 2)
