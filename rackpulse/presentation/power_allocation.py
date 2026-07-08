from __future__ import annotations

from rackpulse.models import DeviceReading, DeviceStatus, RackReading
from rackpulse.state import watts_to_kw

PDU_TYPE = "pdu"
_COUNTABLE = frozenset({DeviceStatus.OK, DeviceStatus.STALE})


def _countable_watts(device: DeviceReading) -> float | None:
    if device.status not in _COUNTABLE:
        return None
    return device.power_watts


def build_rack_device_view(rack: RackReading) -> dict:
    """Build per-device power breakdown with estimated share for unmetered hosts."""
    pdu_watts_values = [
        w
        for device in rack.devices
        if device.device_type == PDU_TYPE
        for w in [_countable_watts(device)]
        if w is not None
    ]
    pdu_total_watts = round(sum(pdu_watts_values), 1) if pdu_watts_values else None

    measured_non_pdu: dict[str, float] = {}
    unmeasured: list[DeviceReading] = []

    for device in rack.devices:
        if device.device_type == PDU_TYPE:
            continue
        watts = _countable_watts(device)
        if watts is not None:
            measured_non_pdu[device.name] = watts
        else:
            unmeasured.append(device)

    measured_total = round(sum(measured_non_pdu.values()), 1) if measured_non_pdu else 0.0
    remainder = None
    share = None
    if pdu_total_watts is not None:
        remainder = round(max(pdu_total_watts - measured_total, 0.0), 1)
        if unmeasured and remainder > 0:
            share = round(remainder / len(unmeasured), 1)

    device_entries: list[dict] = []
    estimated_total = 0.0

    for device in rack.devices:
        if device.device_type == PDU_TYPE:
            watts = _countable_watts(device)
            source = "metered" if watts is not None else "none"
        elif device.name in measured_non_pdu:
            watts = measured_non_pdu[device.name]
            source = "measured"
        elif share is not None:
            watts = share
            source = "estimated"
            estimated_total += share
        else:
            watts = None
            source = "none"

        device_entries.append(
            {
                "name": device.name,
                "type": device.device_type,
                "host": device.host,
                "status": device.status.value,
                "parent": device.parent_name,
                "power_watts": watts,
                "power_kw": watts_to_kw(watts),
                "power_source": source,
                "cpu_percent": device.metrics.cpu_percent,
                "ram_percent": device.metrics.ram_percent,
                "temperature_c": device.metrics.temperature_c,
                "error": device.error,
            }
        )

    return {
        "name": rack.name,
        "location": rack.location,
        "pdu_total_watts": pdu_total_watts,
        "pdu_total_kw": watts_to_kw(pdu_total_watts),
        "measured_watts": measured_total,
        "measured_kw": watts_to_kw(measured_total),
        "estimated_watts": round(estimated_total, 1) if estimated_total else 0.0,
        "estimated_kw": watts_to_kw(estimated_total) if estimated_total else 0.0,
        "unallocated_watts": remainder,
        "unallocated_kw": watts_to_kw(remainder),
        "devices": device_entries,
    }


def build_device_views(racks: list[RackReading]) -> list[dict]:
    return [build_rack_device_view(rack) for rack in racks]
