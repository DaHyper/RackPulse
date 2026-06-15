from __future__ import annotations

import asyncio

from rackpulse.collectors.base import Collector
from rackpulse.config import AppConfig, DeviceConfig
from rackpulse.models import DeviceStatus, MetricReading
from rackpulse.snmp_client import snmp_get

# NAS/storage SNMP OIDs (HOST-RESOURCES-MIB, UCD-SNMP-MIB, vendor extensions)
OID_CPU_LOAD = "1.3.6.1.4.1.2021.11.11.0"  # laLoad.1 (1-min load * 100)
OID_MEM_TOTAL = "1.3.6.1.4.1.2021.4.5.0"  # memTotalReal KB
OID_MEM_AVAIL = "1.3.6.1.4.1.2021.4.6.0"  # memAvailReal KB
OID_MEM_BUFFER = "1.3.6.1.4.1.2021.4.14.0"  # memBuffer KB
OID_MEM_CACHED = "1.3.6.1.4.1.2021.4.15.0"  # memCached KB
OID_SYS_TEMP = "1.3.6.1.4.1.6574.1.2.0"  # vendor system temperature OID


class NasCollector(Collector):
    device_type = "nas"

    async def collect(
        self,
        device: DeviceConfig,
        rack: str,
        config: AppConfig,
    ):
        snmp = config.snmp
        mem_total, mem_avail, mem_buffer, mem_cached, temp, load = await asyncio.gather(
            snmp_get(device, OID_MEM_TOTAL, snmp),
            snmp_get(device, OID_MEM_AVAIL, snmp),
            snmp_get(device, OID_MEM_BUFFER, snmp),
            snmp_get(device, OID_MEM_CACHED, snmp),
            snmp_get(device, OID_SYS_TEMP, snmp),
            snmp_get(device, OID_CPU_LOAD, snmp),
        )

        if not mem_total.success and not temp.success:
            error = mem_total.error or temp.error or "SNMP unreachable"
            return self._base_reading(device, rack, DeviceStatus.UNREACHABLE, error=error)

        ram_percent = None
        if mem_total.success and mem_avail.success and mem_total.value:
            total = float(mem_total.value)
            if total > 0:
                free = float(mem_avail.value or 0)
                buffers = (
                    float(mem_buffer.value)
                    if mem_buffer.success and mem_buffer.value is not None
                    else 0.0
                )
                cached = (
                    float(mem_cached.value)
                    if mem_cached.success and mem_cached.value is not None
                    else 0.0
                )
                used = max(0.0, total - free - buffers - cached)
                ram_percent = round(min(100.0, used / total * 100), 1)

        cpu_percent = None
        if load.success and load.value is not None:
            # laLoad is load * 100; approximate CPU % capped at 100
            cpu_percent = min(round(load.value, 1), 100.0)

        temperature_c = round(temp.value, 1) if temp.success and temp.value is not None else None

        return self._base_reading(
            device,
            rack,
            DeviceStatus.OK,
            MetricReading(
                cpu_percent=cpu_percent,
                ram_percent=ram_percent,
                temperature_c=temperature_c,
            ),
        )


SynologyCollector = NasCollector
