from __future__ import annotations

from collections import defaultdict

from rackpulse.models import DeviceReading


def resolve_parent_name(
    device_name: str,
    rack_names: set[str],
    *,
    configured_parent: str | None = None,
) -> str | None:
    if not configured_parent:
        return None

    by_lower = {name.lower(): name for name in rack_names}
    resolved = by_lower.get(configured_parent.lower())
    if resolved and resolved != device_name:
        return resolved

    return None


def order_rack_devices(
    devices: list[DeviceReading],
    *,
    parent_by_name: dict[str, str | None] | None = None,
) -> list[DeviceReading]:
    """Group child devices (e.g. Proxmox) directly under their configured parent."""
    if not devices:
        return []

    parent_by_name = parent_by_name or {}
    names = {device.name for device in devices}
    children: dict[str, list[DeviceReading]] = defaultdict(list)
    roots: list[DeviceReading] = []

    for device in devices:
        parent = resolve_parent_name(
            device.name,
            names,
            configured_parent=parent_by_name.get(device.name),
        )
        if parent:
            children[parent].append(device)
        else:
            roots.append(device)

    for child_list in children.values():
        child_list.sort(key=lambda d: d.name.lower())

    roots.sort(key=_root_sort_key)

    ordered: list[DeviceReading] = []
    seen: set[str] = set()

    for root in roots:
        ordered.append(_with_parent(root, None))
        seen.add(root.name)
        for child in children.get(root.name, []):
            ordered.append(_with_parent(child, root.name))
            seen.add(child.name)

    leftovers = sorted(
        (device for device in devices if device.name not in seen),
        key=_root_sort_key,
    )
    for device in leftovers:
        ordered.append(_with_parent(device, None))

    return ordered


def _root_sort_key(device: DeviceReading) -> tuple:
    power = device.power_watts
    return (
        0 if power is not None else 1,
        -(power or 0),
        device.name.lower(),
    )


def _with_parent(device: DeviceReading, parent_name: str | None) -> DeviceReading:
    if device.parent_name == parent_name:
        return device
    return DeviceReading(
        name=device.name,
        device_type=device.device_type,
        host=device.host,
        rack=device.rack,
        status=device.status,
        metrics=device.metrics,
        last_poll=device.last_poll,
        error=device.error,
        vms=device.vms,
        parent_name=parent_name,
    )
