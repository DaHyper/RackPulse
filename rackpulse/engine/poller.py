from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timezone

from rackpulse.collectors.registry import get_collector
from rackpulse.config import AppConfig, DeviceConfig, RackConfig, load_config
from rackpulse.models import DeviceReading, DeviceStatus, PollSnapshot, RackReading, RackStatus
from rackpulse.display.order import order_rack_devices
from rackpulse.storage import Storage

logger = logging.getLogger(__name__)

BMC_DEVICE_TYPES = frozenset({
    "hp_server",
    "dell_server",
    "lenovo_server",
    "hp_ilo",
    "dell_idrac",
})
BMC_POLL_CONCURRENCY = 2


class Poller:
    def __init__(self, config_path: str) -> None:
        self.config_path = config_path
        self._lock = threading.Lock()
        self._config = load_config(config_path)
        self._storage = Storage(self._config.storage.path)
        self._snapshot = PollSnapshot(poll_interval_seconds=self._config.poll_interval_seconds)
        self._last_good: dict[str, DeviceReading] = {}
        self._bmc_semaphore = asyncio.Semaphore(BMC_POLL_CONCURRENCY)
        self._task: asyncio.Task[None] | None = None
        self._stop: asyncio.Event | None = None

    @property
    def config(self) -> AppConfig:
        with self._lock:
            return self._config

    @property
    def storage(self) -> Storage:
        return self._storage

    def reload_config(self) -> None:
        with self._lock:
            self._config = load_config(self.config_path)
            self._snapshot.poll_interval_seconds = self._config.poll_interval_seconds

    def get_snapshot(self) -> PollSnapshot:
        with self._lock:
            return PollSnapshot(
                racks=list(self._snapshot.racks),
                last_poll=self._snapshot.last_poll,
                poll_interval_seconds=self._snapshot.poll_interval_seconds,
            )

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(self._run_loop(), name="rackpulse-poller")

    async def stop(self) -> None:
        if self._stop:
            self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self._stop = None

    async def poll_once(self) -> PollSnapshot:
        config = self.config
        now = datetime.now(timezone.utc)

        rack_readings: list[RackReading] = []
        for rack in config.racks:
            devices = await asyncio.gather(
                *[self._poll_device(device, rack, config, now) for device in rack.devices]
            )
            rack_readings.append(self._aggregate_rack(rack, list(devices)))

        snapshot = PollSnapshot(
            racks=rack_readings,
            last_poll=now,
            poll_interval_seconds=config.poll_interval_seconds,
        )

        try:
            self._storage.save_snapshot(snapshot)
            self._storage.prune_old_data(config.storage.retain_days)
        except Exception:
            logger.exception("Failed to persist snapshot")

        with self._lock:
            self._snapshot = snapshot

        return snapshot

    async def poll_device_by_name(self, device_name: str) -> DeviceReading:
        config = self.config
        now = datetime.now(timezone.utc)
        for rack in config.racks:
            for device in rack.devices:
                if device.name == device_name:
                    return await self._poll_device(device, rack.name, config, now)
        raise KeyError(f"Device not found in config: {device_name}")

    async def _run_loop(self) -> None:
        while self._stop and not self._stop.is_set():
            try:
                await self.poll_once()
            except Exception:
                logger.exception("Poll cycle failed")
            interval = self.config.poll_interval_seconds
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
                return
            except asyncio.TimeoutError:
                continue

    async def _poll_device(
        self,
        device: DeviceConfig,
        rack: RackConfig | str,
        config: AppConfig,
        now: datetime,
    ) -> DeviceReading:
        rack_name = rack.name if isinstance(rack, RackConfig) else rack
        try:
            collector = get_collector(device.type)
            if device.type in BMC_DEVICE_TYPES:
                async with self._bmc_semaphore:
                    reading = await collector.collect(device, rack_name, config)
            else:
                reading = await collector.collect(device, rack_name, config)
        except Exception as exc:  # noqa: BLE001
            reading = DeviceReading(
                name=device.name,
                device_type=device.type,
                host=device.host,
                rack=rack_name,
                status=DeviceStatus.ERROR,
                last_poll=now,
                error=str(exc),
            )

        if reading.status == DeviceStatus.UNREACHABLE:
            prev = self._last_good.get(device.name)
            if prev and prev.power_watts is not None:
                reading.status = DeviceStatus.STALE
                reading.metrics = prev.metrics
                reading.last_poll = prev.last_poll
        elif reading.status == DeviceStatus.OK:
            self._last_good[device.name] = reading

        return reading

    def _aggregate_rack(self, rack: RackConfig, devices: list[DeviceReading]) -> RackReading:
        power_values = [
            d.power_watts for d in devices if d.power_watts is not None and d.status != DeviceStatus.UNREACHABLE
        ]
        total_watts = round(sum(power_values), 1) if power_values else None

        warning_watts = rack.warning_kw * 1000 if rack.warning_kw is not None else None
        critical_watts = rack.critical_kw * 1000 if rack.critical_kw is not None else None
        cap_watts = rack.power_cap_kw * 1000 if rack.power_cap_kw is not None else critical_watts

        status = RackStatus.UNKNOWN
        if total_watts is not None:
            if critical_watts is not None and total_watts >= critical_watts:
                status = RackStatus.CRITICAL
            elif warning_watts is not None and total_watts >= warning_watts:
                status = RackStatus.WARNING
            else:
                status = RackStatus.OK

        if any(d.status == DeviceStatus.STALE for d in devices) and status == RackStatus.OK:
            status = RackStatus.WARNING

        if total_watts is None and any(d.status == DeviceStatus.OK for d in devices):
            status = RackStatus.OK

        parent_by_name = {device.name: device.parent for device in rack.devices}
        ordered_devices = order_rack_devices(devices, parent_by_name=parent_by_name)

        return RackReading(
            name=rack.name,
            location=rack.location,
            power_watts=total_watts,
            power_cap_watts=cap_watts,
            status=status,
            devices=ordered_devices,
            warning_watts=warning_watts,
            critical_watts=critical_watts,
        )
