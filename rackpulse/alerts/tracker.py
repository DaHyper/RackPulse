from __future__ import annotations

import time

from rackpulse.alerts.notifier import AlertNotifier
from rackpulse.models import DeviceStatus, RackReading, RackStatus
from rackpulse.state import watts_to_kw

_PDU_TYPES = frozenset({"pdu", "apc_pdu"})


class AlertTracker:
    """Tracks alert state and enforces cooldown between repeat notifications.

    Wattage alerts can also require the reading to hold. ``hold_minutes`` of 0
    keeps the old behavior: notify on the first poll that crosses a threshold.
    """

    def __init__(self, cooldown_minutes: int, hold_minutes: int = 0) -> None:
        self.cooldown_seconds = cooldown_minutes * 60
        self.hold_seconds = max(0, hold_minutes) * 60
        self._rack_state: dict[str, RackStatus] = {}
        self._pending_rack: dict[str, tuple[RackStatus, float]] = {}
        self._device_state: dict[str, DeviceStatus] = {}
        self._last_sent: dict[str, float] = {}

    def _key(self, prefix: str, name: str, status: str) -> str:
        return f"{prefix}:{name}:{status}"

    def _can_send(self, key: str) -> bool:
        last = self._last_sent.get(key, 0)
        return (time.monotonic() - last) >= self.cooldown_seconds

    def _mark_sent(self, key: str) -> None:
        self._last_sent[key] = time.monotonic()

    @staticmethod
    def _rack_telemetry_incomplete(rack: RackReading) -> bool:
        """True when any PDU is offline — cached kW must not drive threshold alerts."""
        return any(
            d.device_type in _PDU_TYPES
            and d.status in (DeviceStatus.STALE, DeviceStatus.UNREACHABLE)
            for d in rack.devices
        )

    @staticmethod
    def _device_offline(status: DeviceStatus) -> bool:
        return status in (DeviceStatus.STALE, DeviceStatus.UNREACHABLE)

    def process(
        self,
        racks: list[RackReading],
        notifier: AlertNotifier,
        *,
        now: float | None = None,
    ) -> None:
        if now is None:
            now = time.monotonic()
        for rack in racks:
            curr = rack.status
            incomplete = self._rack_telemetry_incomplete(rack)

            # Incomplete polls keep last-known kW for the UI. That sample is not
            # evidence the draw is still high, so it must not finish a hold or
            # count as a threshold crossing.
            if incomplete:
                self._pending_rack.pop(rack.name, None)
            else:
                self._evaluate_rack_threshold(rack, curr, notifier, now)

            for device in rack.devices:
                device_key = f"{rack.name}:{device.name}"
                prev_device = self._device_state.get(device_key, DeviceStatus.OK)
                curr_device = device.status

                if self._device_offline(curr_device) and not self._device_offline(prev_device):
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

                if curr_device == DeviceStatus.OK and self._device_offline(prev_device):
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

    def _evaluate_rack_threshold(
        self,
        rack: RackReading,
        curr: RackStatus,
        notifier: AlertNotifier,
        now: float,
    ) -> None:
        committed = self._rack_state.get(rack.name)

        if committed is None:
            if curr in (RackStatus.WARNING, RackStatus.CRITICAL) and self.hold_seconds > 0:
                pending = self._pending_rack.get(rack.name)
                if pending is None or pending[0] != curr:
                    self._pending_rack[rack.name] = (curr, now)
                    return
                if (now - pending[1]) < self.hold_seconds:
                    return
            self._emit_rack_transition(rack, RackStatus.UNKNOWN, curr, notifier)
            self._rack_state[rack.name] = curr
            self._pending_rack.pop(rack.name, None)
            return

        if curr == committed:
            self._pending_rack.pop(rack.name, None)
            return

        if self.hold_seconds <= 0:
            self._emit_rack_transition(rack, committed, curr, notifier)
            self._rack_state[rack.name] = curr
            self._pending_rack.pop(rack.name, None)
            return

        pending = self._pending_rack.get(rack.name)
        if pending is None or pending[0] != curr:
            self._pending_rack[rack.name] = (curr, now)
            return

        if (now - pending[1]) >= self.hold_seconds:
            self._emit_rack_transition(rack, committed, curr, notifier)
            self._rack_state[rack.name] = curr
            self._pending_rack.pop(rack.name, None)

    def _emit_rack_transition(
        self,
        rack: RackReading,
        prev: RackStatus,
        curr: RackStatus,
        notifier: AlertNotifier,
    ) -> None:
        power_kw = watts_to_kw(rack.power_watts) or 0.0
        warning_kw = watts_to_kw(rack.warning_watts) or 0.0
        critical_kw = watts_to_kw(rack.critical_watts) or 0.0
        held = ""
        if self.hold_seconds > 0:
            minutes = self.hold_seconds / 60
            held = f"The reading held for at least {minutes:g} minutes.\n"

        if curr in (RackStatus.WARNING, RackStatus.CRITICAL) and curr != prev:
            key = self._key("rack", rack.name, curr.value)
            if self._can_send(key):
                level = "WARNING" if curr == RackStatus.WARNING else "CRITICAL"
                severity = "warning" if curr == RackStatus.WARNING else "critical"
                notifier.send(
                    subject=f"[RackPulse] {level}: {rack.name} at {power_kw:.2f} kW",
                    body=(
                        f"Rack {rack.name} has crossed the {level.lower()} threshold.\n"
                        f"{held}\n"
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
                        f"Rack {rack.name} is back under the warning threshold.\n"
                        f"{held}\n"
                        f"Current draw: {power_kw:.2f} kW\n"
                    ),
                    severity="recovery",
                )
                self._mark_sent(key)
