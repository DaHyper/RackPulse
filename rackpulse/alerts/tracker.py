from __future__ import annotations

import time

from rackpulse.alerts.notifier import AlertNotifier
from rackpulse.models import DeviceReading, DeviceStatus, RackReading, RackStatus
from rackpulse.state import watts_to_kw


class AlertTracker:
    """Tracks alert state and enforces cooldown between repeat notifications."""

    def __init__(self, cooldown_minutes: int) -> None:
        self.cooldown_seconds = cooldown_minutes * 60
        self._rack_state: dict[str, RackStatus] = {}
        self._device_state: dict[str, DeviceStatus] = {}
        self._last_sent: dict[str, float] = {}

    def _key(self, prefix: str, name: str, status: str) -> str:
        return f"{prefix}:{name}:{status}"

    def _can_send(self, key: str) -> bool:
        last = self._last_sent.get(key, 0)
        return (time.monotonic() - last) >= self.cooldown_seconds

    def _mark_sent(self, key: str) -> None:
        self._last_sent[key] = time.monotonic()

    def process(self, racks: list[RackReading], notifier: AlertNotifier) -> None:
        for rack in racks:
            prev = self._rack_state.get(rack.name, RackStatus.UNKNOWN)
            curr = rack.status
            power_kw = watts_to_kw(rack.power_watts) or 0.0
            warning_kw = watts_to_kw(rack.warning_watts) or 0.0
            critical_kw = watts_to_kw(rack.critical_watts) or 0.0

            if curr in (RackStatus.WARNING, RackStatus.CRITICAL) and curr != prev:
                key = self._key("rack", rack.name, curr.value)
                if self._can_send(key):
                    level = "WARNING" if curr == RackStatus.WARNING else "CRITICAL"
                    severity = "warning" if curr == RackStatus.WARNING else "critical"
                    notifier.send(
                        subject=f"[RackPulse] {level}: {rack.name} at {power_kw:.2f} kW",
                        body=(
                            f"Rack {rack.name} has crossed the {level.lower()} threshold.\n\n"
                            f"Current draw: {power_kw:.2f} kW\n"
                            f"Warning threshold: {warning_kw:.2f} kW\n"
                            f"Critical threshold: {critical_kw:.2f} kW\n"
                        ),
                        severity=severity,
                    )
                    self._mark_sent(key)

            if prev in (RackStatus.WARNING, RackStatus.CRITICAL) and curr == RackStatus.OK:
                key = self._key("rack", rack.name, "recovery")
                if self._can_send(key):
                    notifier.send(
                        subject=f"[RackPulse] RECOVERED: {rack.name} back to normal",
                        body=(
                            f"Rack {rack.name} is back under the warning threshold.\n\n"
                            f"Current draw: {power_kw:.2f} kW\n"
                        ),
                        severity="recovery",
                    )
                    self._mark_sent(key)

            self._rack_state[rack.name] = curr

            for device in rack.devices:
                device_key = f"{rack.name}:{device.name}"
                prev_device = self._device_state.get(device_key, DeviceStatus.OK)
                curr_device = device.status

                if curr_device == DeviceStatus.UNREACHABLE and prev_device != DeviceStatus.UNREACHABLE:
                    key = self._key("device", device_key, "unreachable")
                    if self._can_send(key):
                        notifier.send(
                            subject=(
                                f"[RackPulse] DEVICE UNREACHABLE: {device.name} "
                                f"({device.device_type})"
                            ),
                            body=(
                                f"Device {device.name} ({device.device_type}) at {device.host} "
                                f"is unreachable.\n"
                                f"Rack: {rack.name}\n"
                                f"Error: {device.error or 'timeout'}\n"
                            ),
                            severity="critical",
                        )
                        self._mark_sent(key)

                if (
                    curr_device in (DeviceStatus.OK, DeviceStatus.STALE)
                    and prev_device == DeviceStatus.UNREACHABLE
                ):
                    key = self._key("device", device_key, "recovery")
                    if self._can_send(key):
                        notifier.send(
                            subject=(
                                f"[RackPulse] DEVICE RECOVERED: {device.name} "
                                f"({device.device_type})"
                            ),
                            body=(
                                f"Device {device.name} at {device.host} is responding again."
                            ),
                            severity="recovery",
                        )
                        self._mark_sent(key)

                self._device_state[device_key] = curr_device
