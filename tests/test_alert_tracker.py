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


def test_stale_device_does_not_elevate_ok_to_warning():
    devices = [_device("pdu-1", 1000, DeviceStatus.STALE)]
    status = compute_rack_status(1000, 4000, 5000, devices)
    assert status == RackStatus.OK


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


def test_stale_pdu_does_not_send_wattage_alert():
    """Link drop rewrites UNREACHABLE→STALE with cached kW; that must not
    drive threshold alerts even if cached draw is over the warning line."""
    tracker = AlertTracker(cooldown_minutes=0)
    notifier = MagicMock()
    rack_cfg = RackConfig(name="rack-1", warning_kw=2.0, critical_kw=3.0, devices=[])

    ok_rack = aggregate_rack_reading(rack_cfg, [_device("pdu-1", 1000)])
    tracker.process([ok_rack], notifier)
    assert notifier.send.call_count == 0

    # Under-threshold stale
    stale_ok = aggregate_rack_reading(
        rack_cfg, [_device("pdu-1", 1000, DeviceStatus.STALE)]
    )
    assert stale_ok.status == RackStatus.OK
    tracker.process([stale_ok], notifier)

    # Over-threshold cached kW while offline — still incomplete, no wattage alert
    stale_high = aggregate_rack_reading(
        rack_cfg, [_device("pdu-1", 2500, DeviceStatus.STALE)]
    )
    assert stale_high.status == RackStatus.WARNING
    tracker.process([stale_high], notifier)

    subjects = [call.kwargs["subject"] for call in notifier.send.call_args_list]
    assert not any("WARNING:" in s or "CRITICAL:" in s for s in subjects)
    assert any("DEVICE UNREACHABLE" in s for s in subjects)

    recovered = aggregate_rack_reading(rack_cfg, [_device("pdu-1", 1000)])
    tracker.process([recovered], notifier)
    subjects = [call.kwargs["subject"] for call in notifier.send.call_args_list]
    assert not any("RECOVERED: rack-1 back to normal" in s for s in subjects)
    assert any("DEVICE RECOVERED" in s for s in subjects)


def test_real_wattage_warning_still_alerts():
    tracker = AlertTracker(cooldown_minutes=0)
    notifier = MagicMock()
    rack_cfg = RackConfig(name="rack-1", warning_kw=2.0, critical_kw=3.0, devices=[])

    ok_rack = aggregate_rack_reading(rack_cfg, [_device("pdu-1", 1000)])
    tracker.process([ok_rack], notifier)

    warning_rack = aggregate_rack_reading(rack_cfg, [_device("pdu-1", 2500)])
    tracker.process([warning_rack], notifier)

    subjects = [call.kwargs["subject"] for call in notifier.send.call_args_list]
    assert any("WARNING:" in s for s in subjects)
