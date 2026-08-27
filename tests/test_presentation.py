from __future__ import annotations

from datetime import datetime, timezone

from rackpulse.config import RackConfig
from rackpulse.models import DeviceReading, DeviceStatus, MetricReading, PollSnapshot, RackStatus
from rackpulse.presentation.dashboard import build_dashboard_state
from rackpulse.state import aggregate_rack_reading


def _device(name: str, watts: float) -> DeviceReading:
    return DeviceReading(
        name=name,
        device_type="pdu",
        host="10.0.0.1",
        rack="rack-1",
        status=DeviceStatus.OK,
        metrics=MetricReading(power_watts=watts),
    )


def test_build_dashboard_state_includes_headroom():
    rack_cfg = RackConfig(name="rack-1", location="row 1", warning_kw=2.0, critical_kw=3.0, devices=[])
    rack = aggregate_rack_reading(rack_cfg, [_device("pdu-1", 1500)])
    snapshot = PollSnapshot(
        racks=[rack],
        last_poll=datetime.now(timezone.utc),
        poll_interval_seconds=60,
    )

    class FakeStorage:
        def recent_power_by_rack(self, rack_name: str, hours: float = 24):
            return [("2026-01-01T00:00:00+00:00", 1500.0)]

    from rackpulse.config import AppConfig

    state = build_dashboard_state(snapshot, AppConfig(), FakeStorage())
    assert state["racks"][0]["power_kw"] == 1.5
    assert state["racks"][0]["headroom_kw"] == 1.5
    assert state["racks"][0]["status"] == RackStatus.OK.value
    assert "rack-1" in state["history"]
