from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from typing import Any

from rackpulse.collectors.base import Collector
from rackpulse.config import AppConfig, DeviceConfig
from rackpulse.models import DeviceReading, DeviceStatus, MetricReading


@dataclass
class PowerReading:
    watts: float | None = None
    volts: float | None = None
    amps: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class PowerCollector(Collector):
    """Collectors that report electrical power draw."""

    @abstractmethod
    async def get_power(
        self,
        device: DeviceConfig,
        config: AppConfig,
    ) -> PowerReading:
        raise NotImplementedError

    async def collect(
        self,
        device: DeviceConfig,
        rack: str,
        config: AppConfig,
    ) -> DeviceReading:
        try:
            power = await self.get_power(device, config)
        except Exception as exc:  # noqa: BLE001
            return self._base_reading(device, rack, DeviceStatus.UNREACHABLE, error=str(exc))

        if power.watts is None:
            return self._base_reading(
                device,
                rack,
                DeviceStatus.ERROR,
                error="No power reading available",
            )

        return self._base_reading(
            device,
            rack,
            DeviceStatus.OK,
            MetricReading(
                power_watts=power.watts,
                volts=power.volts,
                amps=power.amps,
                extra=power.extra,
            ),
        )
