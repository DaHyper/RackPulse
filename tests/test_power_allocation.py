from __future__ import annotations

from rackpulse.config import RackConfig
from rackpulse.models import DeviceReading, DeviceStatus, MetricReading
from rackpulse.presentation.power_allocation import build_rack_device_view
from rackpulse.state import aggregate_rack_reading


def _device(name: str, device_type: str, watts: float | None, parent: str | None = None) -> DeviceReading:
    return DeviceReading(
        name=name,
        device_type=device_type,
        host="10.0.0.1",
        rack="rack-1",
        status=DeviceStatus.OK,
        metrics=MetricReading(power_watts=watts),
        parent_name=parent,
    )


def test_allocates_unmetered_power_evenly():
    rack_cfg = RackConfig(
        name="rack-1",
        location="row 1",
        warning_kw=4.0,
        critical_kw=5.0,
        devices=[],
    )
    devices = [
        _device("pdu-1", "pdu", 2000.0),
        _device("server-a", "hp_server", 500.0),
        _device("switch-1", "arista_switch", None),
        _device("pve-1", "pve", None, parent="server-a"),
    ]
    rack = aggregate_rack_reading(rack_cfg, devices)
    view = build_rack_device_view(rack)

    assert view["pdu_total_watts"] == 2000.0
    assert view["measured_watts"] == 500.0
    assert view["unallocated_watts"] == 1500.0

    by_name = {d["name"]: d for d in view["devices"]}
    assert by_name["pdu-1"]["power_source"] == "metered"
    assert by_name["server-a"]["power_source"] == "measured"
    assert by_name["switch-1"]["power_source"] == "estimated"
    assert by_name["switch-1"]["power_watts"] == 750.0
    assert by_name["pve-1"]["power_source"] == "estimated"
    assert by_name["pve-1"]["power_watts"] == 750.0
