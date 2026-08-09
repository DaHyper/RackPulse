from __future__ import annotations

from rackpulse.config import RackConfig
from rackpulse.models import DeviceReading, DeviceStatus, RackReading, RackStatus


def kw_to_watts(kw: float | None) -> float | None:
    if kw is None:
        return None
    return kw * 1000


def watts_to_kw(watts: float | None) -> float | None:
    if watts is None:
        return None
    return round(watts / 1000, 2)


def compute_rack_status(
    total_watts: float | None,
    warning_watts: float | None,
    critical_watts: float | None,
    devices: list[DeviceReading],
) -> RackStatus:
    # Threshold status is based on last-known kW only. Stale/unreachable PDUs are
    # surfaced on the device itself and must not upgrade the rack to WARNING — that
    # previously caused false over-wattage alerts whenever the link dropped.
    status = RackStatus.UNKNOWN
    if total_watts is not None:
        if critical_watts is not None and total_watts >= critical_watts:
            status = RackStatus.CRITICAL
        elif warning_watts is not None and total_watts >= warning_watts:
            status = RackStatus.WARNING
        else:
            status = RackStatus.OK

    if total_watts is None and any(d.status == DeviceStatus.OK for d in devices):
        status = RackStatus.OK

    return status


def compute_rack_metrics(
    total_watts: float | None,
    critical_kw: float | None,
    power_cap_kw: float | None = None,
) -> tuple[float | None, float | None]:
    """Return (headroom_kw, percent_of_limit)."""
    power_kw = watts_to_kw(total_watts)
    if power_kw is None:
        return None, None

    limit_kw = critical_kw if critical_kw is not None else power_cap_kw
    if limit_kw is None or limit_kw <= 0:
        return None, None

    headroom = round(limit_kw - power_kw, 2)
    percent = round(power_kw / limit_kw * 100, 1)
    return headroom, percent


def aggregate_rack_reading(
    rack: RackConfig,
    devices: list[DeviceReading],
) -> RackReading:
    power_values = [
        d.power_watts
        for d in devices
        if d.power_watts is not None and d.status != DeviceStatus.UNREACHABLE
    ]
    total_watts = round(sum(power_values), 1) if power_values else None

    warning_watts = kw_to_watts(rack.warning_kw)
    critical_watts = kw_to_watts(rack.critical_kw)
    cap_watts = kw_to_watts(rack.power_cap_kw) if rack.power_cap_kw is not None else critical_watts

    status = compute_rack_status(total_watts, warning_watts, critical_watts, devices)

    return RackReading(
        name=rack.name,
        location=rack.location,
        power_watts=total_watts,
        power_cap_watts=cap_watts,
        status=status,
        devices=devices,
        warning_watts=warning_watts,
        critical_watts=critical_watts,
    )
