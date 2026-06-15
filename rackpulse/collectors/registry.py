from __future__ import annotations

from rackpulse.collectors.apc_pdu import PduCollector
from rackpulse.collectors.base import Collector
from rackpulse.collectors.entity_sensor_switch import EntitySensorSwitchCollector
from rackpulse.collectors.nvidia_gpu import NvidiaGpuCollector
from rackpulse.collectors.proxmox import ProxmoxCollector
from rackpulse.collectors.redfish_power import (
    DellServerCollector,
    HpServerCollector,
    LenovoServerCollector,
)
from rackpulse.collectors.synology import NasCollector

_pdu = PduCollector()
_hp = HpServerCollector()
_dell = DellServerCollector()
_lenovo = LenovoServerCollector()
_pve = ProxmoxCollector()
_nas = NasCollector()
_gpu = NvidiaGpuCollector()
_entity_switch = EntitySensorSwitchCollector()

COLLECTORS: dict[str, Collector] = {
    "pdu": _pdu,
    "hp_server": _hp,
    "dell_server": _dell,
    "lenovo_server": _lenovo,
    "pve": _pve,
    "nas": _nas,
    "gpu": _gpu,
    "arista_switch": _entity_switch,
    "cisco_switch": _entity_switch,
    "dell_switch": _entity_switch,
    # Legacy type names (still accepted)
    "apc_pdu": _pdu,
    "hp_ilo": _hp,
    "dell_idrac": _dell,
    "proxmox": _pve,
    "synology": _nas,
    "nvidia_gpu": _gpu,
    "switch": _entity_switch,
}

SUPPORTED_TYPES = sorted(k for k in COLLECTORS if k not in {
    "apc_pdu", "hp_ilo", "dell_idrac", "proxmox", "synology", "nvidia_gpu", "switch",
})


def get_collector(device_type: str) -> Collector:
    collector = COLLECTORS.get(device_type)
    if collector is None:
        raise ValueError(
            f"Unknown device type '{device_type}'. Supported: {', '.join(SUPPORTED_TYPES)}"
        )
    return collector
