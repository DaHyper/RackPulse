from __future__ import annotations

import time
from unittest.mock import MagicMock

from rackpulse.alerts.tracker import AlertTracker
from rackpulse.config import RackConfig
from rackpulse.models import DeviceReading, DeviceStatus, MetricReading, RackReading, RackStatus
from rackpulse.state import aggregate_rack_reading, compute_rack_metrics, compute_rack_status


def _device(name: str, watts: float | None, status: DeviceStatus = DeviceStatus.OK) -> DeviceReading:
    return DeviceReading(
        name=name,
        device_type="pdu",
        host="10.0.0.1",
        rack="rack-1",
        status=status,
        metrics=MetricReading(power_watts=watts),
    )


def test_compute_rack_status_critical():
    devices = [_device("pdu-1", 5500)]
    status = compute_rack_status(5500, 4000, 5000, devices)
    assert status == RackStatus.CRITICAL


def test_stale_device_elevates_ok_to_warning():
    devices = [_device("pdu-1", 1000, DeviceStatus.STALE)]
    status = compute_rack_status(1000, 4000, 5000, devices)
    assert status == RackStatus.WARNING


def test_compute_rack_metrics():
    headroom, pct = compute_rack_metrics(3500, critical_kw=5.0)
    assert headroom == 1.5
    assert pct == 70.0


def test_alert_tracker_rack_transition_respects_cooldown():
    tracker = AlertTracker(cooldown_minutes=15)
    notifier = MagicMock()
    rack_cfg = RackConfig(name="rack-1", warning_kw=2.0, critical_kw=3.0, devices=[])

    warning_rack = aggregate_rack_reading(rack_cfg, [_device("pdu-1", 2500)])
    tracker.process([warning_rack], notifier)
    assert notifier.send.call_count == 1

    tracker.process([warning_rack], notifier)
    assert notifier.send.call_count == 1

    critical_rack = aggregate_rack_reading(rack_cfg, [_device("pdu-1", 3500)])
    tracker.cooldown_seconds = 0
    tracker.process([critical_rack], notifier)
    assert notifier.send.call_count == 2


def test_alert_tracker_recovery_alert():
    tracker = AlertTracker(cooldown_minutes=0)
    notifier = MagicMock()
    rack_cfg = RackConfig(name="rack-1", warning_kw=2.0, critical_kw=3.0, devices=[])

    warning_devices = [_device("pdu-1", 2500)]
    warning_rack = aggregate_rack_reading(rack_cfg, warning_devices)
    tracker.process([warning_rack], notifier)

    ok_devices = [_device("pdu-1", 1000)]
    ok_rack = aggregate_rack_reading(rack_cfg, ok_devices)
    tracker.process([ok_rack], notifier)

    subjects = [call.kwargs["subject"] for call in notifier.send.call_args_list]
    assert any("RECOVERED" in subject for subject in subjects)


def test_alert_tracker_device_unreachable():
    tracker = AlertTracker(cooldown_minutes=0)
    notifier = MagicMock()
    rack = RackReading(
        name="rack-1",
        location="",
        power_watts=None,
        power_cap_watts=5000,
        status=RackStatus.UNKNOWN,
        devices=[
            DeviceReading(
                name="hp-server",
                device_type="hp_server",
                host="10.0.0.2",
                rack="rack-1",
                status=DeviceStatus.UNREACHABLE,
                error="timeout",
            )
        ],
    )
    tracker.process([rack], notifier)
    assert notifier.send.call_count == 1
    assert "UNREACHABLE" in notifier.send.call_args.kwargs["subject"]
