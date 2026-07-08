from __future__ import annotations

from rackpulse.models import DeviceReading, RackReading, RackStatus
from rackpulse.state import watts_to_kw

PDU_TYPE = "pdu"


def _device_poll_row(device: DeviceReading) -> dict:
    """One row matching the rackpulse poll terminal table."""
    return {
        "name": device.name,
        "type": device.device_type,
        "host": device.host,
        "status": device.status.value,
        "parent": device.parent_name,
        "power_watts": device.power_watts,
        "power_kw": watts_to_kw(device.power_watts),
        "cpu_percent": device.metrics.cpu_percent or device.metrics.gpu_util_percent,
        "ram_percent": device.metrics.ram_percent,
        "temperature_c": device.metrics.temperature_c,
        "volts": device.metrics.volts,
        "amps": device.metrics.amps,
        "gpu_power_watts": device.metrics.gpu_power_watts,
        "error": device.error,
        "vms": [
            {
                "vmid": vm.vmid,
                "name": vm.name,
                "cpu_percent": vm.cpu_percent,
                "ram_percent": vm.ram_percent,
                "status": vm.status,
            }
            for vm in device.vms
        ],
    }


def build_rack_poll_view(rack: RackReading) -> dict:
    """Poll-style rack breakdown: actual per-device readings, no estimated splits."""
    pdu_total_watts = 0.0
    measured_device_watts = 0.0
    has_pdu = False

    for device in rack.devices:
        watts = device.power_watts
        if watts is None:
            continue
        if device.device_type == PDU_TYPE:
            has_pdu = True
            pdu_total_watts += watts
        else:
            measured_device_watts += watts

    pdu_total_watts = round(pdu_total_watts, 1) if has_pdu else None
    measured_device_watts = round(measured_device_watts, 1) if measured_device_watts else 0.0

    unaccounted_watts = None
    if pdu_total_watts is not None:
        unaccounted_watts = round(max(pdu_total_watts - measured_device_watts, 0.0), 1)

    return {
        "name": rack.name,
        "location": rack.location,
        "power_watts": rack.power_watts,
        "power_kw": watts_to_kw(rack.power_watts),
        "status": rack.status.value,
        "pdu_total_watts": pdu_total_watts,
        "pdu_total_kw": watts_to_kw(pdu_total_watts),
        "measured_device_watts": measured_device_watts,
        "measured_device_kw": watts_to_kw(measured_device_watts),
        "unaccounted_watts": unaccounted_watts,
        "unaccounted_kw": watts_to_kw(unaccounted_watts),
        "devices": [_device_poll_row(device) for device in rack.devices],
    }


def build_device_views(racks: list[RackReading]) -> list[dict]:
    return [build_rack_poll_view(rack) for rack in racks]
