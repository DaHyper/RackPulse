from rackpulse.display.order import order_rack_devices
from rackpulse.models import DeviceReading, DeviceStatus, MetricReading


def _device(name: str, power: float | None = None) -> DeviceReading:
    return DeviceReading(
        name=name,
        device_type="pve" if name.startswith("pve") else "hp_server",
        host=f"10.0.0.{name[-1]}",
        rack="rack-1",
        status=DeviceStatus.OK,
        metrics=MetricReading(power_watts=power),
    )


def test_order_groups_pve_under_configured_parent() -> None:
    devices = [
        _device("pve-3"),
        _device("hp-server-1", 250),
        _device("hp-server-3", 270),
        _device("pve-1"),
        _device("nas-1"),
    ]
    ordered = order_rack_devices(
        devices,
        parent_by_name={
            "pve-1": "hp-server-1",
            "pve-3": "hp-server-3",
        },
    )
    names = [device.name for device in ordered]
    assert names.index("hp-server-3") < names.index("pve-3")
    assert names.index("hp-server-1") < names.index("pve-1")
    assert ordered[names.index("pve-3")].parent_name == "hp-server-3"
    assert ordered[names.index("pve-1")].parent_name == "hp-server-1"


def test_order_ignores_unconfigured_devices() -> None:
    devices = [_device("pve-1"), _device("hp-server-1", 250)]
    ordered = order_rack_devices(devices)
    assert all(device.parent_name is None for device in ordered)


def test_order_respects_explicit_parent() -> None:
    devices = [_device("gpu-host"), _device("pve-gpu")]
    ordered = order_rack_devices(
        devices,
        parent_by_name={"pve-gpu": "gpu-host"},
    )
    assert [device.name for device in ordered] == ["gpu-host", "pve-gpu"]
    assert ordered[1].parent_name == "gpu-host"
