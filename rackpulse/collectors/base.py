from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone

from rackpulse.config import AppConfig, DeviceConfig
from rackpulse.models import DeviceReading, DeviceStatus, MetricReading


class Collector(ABC):
    device_type: str

    @abstractmethod
    async def collect(
        self,
        device: DeviceConfig,
        rack: str,
        config: AppConfig,
    ) -> DeviceReading:
        raise NotImplementedError

    def _base_reading(
        self,
        device: DeviceConfig,
        rack: str,
        status: DeviceStatus,
        metrics: MetricReading | None = None,
        error: str | None = None,
        now: datetime | None = None,
    ) -> DeviceReading:
        return DeviceReading(
            name=device.name,
            device_type=device.type,
            host=device.host,
            rack=rack,
            status=status,
            metrics=metrics or MetricReading(),
            last_poll=now or datetime.now(timezone.utc),
            error=error,
        )
