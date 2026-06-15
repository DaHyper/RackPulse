from __future__ import annotations

import asyncio

from rackpulse.collectors.base import Collector
from rackpulse.config import AppConfig, DeviceConfig
from rackpulse.models import DeviceStatus, MetricReading
from rackpulse.snmp_client import snmp_get


class PduCollector(Collector):
    device_type = "pdu"

    async def collect(
        self,
        device: DeviceConfig,
        rack: str,
        config: AppConfig,
    ):
        pdu = config.pdu
        snmp = config.snmp
        power_result, energy_result = await asyncio.gather(
            snmp_get(device, pdu.power_oid, snmp),
            snmp_get(device, pdu.energy_oid, snmp),
        )

        if not power_result.success:
            return self._base_reading(
                device,
                rack,
                DeviceStatus.UNREACHABLE,
                error=power_result.error,
            )

        power_watts = None
        if power_result.value is not None:
            # OID returns hundredths of kW; divisor converts to watts
            power_kw = power_result.value / pdu.power_divisor
            power_watts = round(power_kw * 1000, 1)

        energy_kwh = None
        if energy_result.success and energy_result.value is not None:
            energy_kwh = round(energy_result.value / pdu.energy_divisor, 2)

        return self._base_reading(
            device,
            rack,
            DeviceStatus.OK,
            MetricReading(power_watts=power_watts, energy_kwh=energy_kwh),
        )


ApcPduCollector = PduCollector
