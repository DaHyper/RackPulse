from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime, timezone

from rackpulse.alerts import AlertNotifier, AlertTracker
from rackpulse.collectors.registry import get_collector
from rackpulse.config import AppConfig, DeviceConfig, RackConfig, load_config
from rackpulse.display.order import order_rack_devices
from rackpulse.maintenance import should_silence_alerts
from rackpulse.models import DeviceReading, DeviceStatus, PollSnapshot
from rackpulse.state import aggregate_rack_reading
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
        self._alert_tracker: AlertTracker | None = None
        self._init_alerts()

    def _init_alerts(self) -> None:
        self._alert_tracker = AlertTracker(self._config.alerts.cooldown_minutes)

    @staticmethod
    def _has_alert_config(config: AppConfig) -> bool:
        smtp = config.alerts.smtp
        return bool(smtp.host and smtp.recipients) or any(
            wh.enabled and wh.url for wh in config.alerts.webhooks
        )

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
            if self._alert_tracker is not None:
                self._alert_tracker.cooldown_seconds = self._config.alerts.cooldown_minutes * 60
            else:
                self._init_alerts()

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

        rack_readings = []
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

        self._process_alerts(snapshot, config)

        with self._lock:
            self._snapshot = snapshot

        return snapshot

    def _process_alerts(self, snapshot: PollSnapshot, config: AppConfig) -> None:
        if self._alert_tracker is None:
            return
        if should_silence_alerts(config.maintenance):
            return
        if not self._has_alert_config(config):
            return
        notifier = AlertNotifier(config.alerts.smtp, config.alerts.webhooks)
        if not notifier.configured:
            return
        self._alert_tracker.process(snapshot.racks, notifier)

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

    def _aggregate_rack(self, rack: RackConfig, devices: list[DeviceReading]):
        parent_by_name = {device.name: device.parent for device in rack.devices}
        ordered_devices = order_rack_devices(devices, parent_by_name=parent_by_name)
        reading = aggregate_rack_reading(rack, ordered_devices)
        return reading
