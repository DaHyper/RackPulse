from __future__ import annotations

from typing import Any

from rackpulse.config import AppConfig
from rackpulse.maintenance import is_maintenance_active, should_silence_alerts
from rackpulse.models import DeviceReading, PollSnapshot, RackReading
from rackpulse.state import compute_rack_metrics, watts_to_kw
from rackpulse.storage import Storage


def _device_to_dict(device: DeviceReading) -> dict[str, Any]:
    power_kw = watts_to_kw(device.power_watts)
    return {
        "name": device.name,
        "type": device.device_type,
        "host": device.host,
        "status": device.status.value,
        "power_kw": power_kw,
        "power_watts": device.power_watts,
        "energy_kwh": device.metrics.energy_kwh,
        "cpu_percent": device.metrics.cpu_percent,
        "ram_percent": device.metrics.ram_percent,
        "temperature_c": device.metrics.temperature_c,
        "gpu_power_watts": device.metrics.gpu_power_watts,
        "volts": device.metrics.volts,
        "amps": device.metrics.amps,
        "last_poll": device.last_poll.isoformat() if device.last_poll else None,
        "error": device.error,
        "parent": device.parent_name,
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


def _rack_to_dict(rack: RackReading, config: AppConfig) -> dict[str, Any]:
    rack_cfg = next((r for r in config.racks if r.name == rack.name), None)
    warning_kw = rack_cfg.warning_kw if rack_cfg else watts_to_kw(rack.warning_watts)
    critical_kw = rack_cfg.critical_kw if rack_cfg else watts_to_kw(rack.critical_watts)
    power_cap_kw = rack_cfg.power_cap_kw if rack_cfg else watts_to_kw(rack.power_cap_watts)
    headroom_kw, percent_of_limit = compute_rack_metrics(
        rack.power_watts,
        critical_kw,
        power_cap_kw,
    )
    power_kw = watts_to_kw(rack.power_watts)

    return {
        "name": rack.name,
        "location": rack.location,
        "description": rack.location,
        "power_kw": power_kw,
        "power_watts": rack.power_watts,
        "warning_kw": warning_kw,
        "critical_kw": critical_kw,
        "power_cap_kw": power_cap_kw,
        "status": rack.status.value,
        "headroom_kw": headroom_kw,
        "percent_of_limit": percent_of_limit,
        "devices": [_device_to_dict(d) for d in rack.devices],
        # Legacy dashboard field name
        "pdus": [_device_to_dict(d) for d in rack.devices],
    }


def build_history(storage: Storage, rack_names: list[str], hours: float = 24) -> dict[str, list[dict[str, Any]]]:
    history: dict[str, list[dict[str, Any]]] = {}
    for name in rack_names:
        samples = storage.recent_power_by_rack(name, hours=hours)
        history[name] = [
            {"t": ts, "kw": round(watts / 1000, 3) if watts is not None else None}
            for ts, watts in samples
        ]
    return history


def build_dashboard_state(
    snapshot: PollSnapshot,
    config: AppConfig,
    storage: Storage,
) -> dict[str, Any]:
    racks = [_rack_to_dict(rack, config) for rack in snapshot.racks]
    rack_names = [rack.name for rack in snapshot.racks]
    maintenance = config.maintenance

    return {
        "racks": racks,
        "last_poll": snapshot.last_poll.isoformat() if snapshot.last_poll else None,
        "poll_interval_seconds": snapshot.poll_interval_seconds,
        "total_power_watts": snapshot.total_power_watts,
        "total_power_kw": snapshot.total_power_kw,
        "history": build_history(storage, rack_names),
        "maintenance_enabled": is_maintenance_active(maintenance),
        "maintenance_message": maintenance.message if is_maintenance_active(maintenance) else "",
        "alerts_silenced": should_silence_alerts(maintenance),
    }
