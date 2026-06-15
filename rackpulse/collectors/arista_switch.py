from __future__ import annotations

import asyncio

from rackpulse.collectors.entity_sensor import (
    OID_SENSOR_OPER_STATUS,
    OID_SENSOR_PHYSICAL_INDEX,
    OID_SENSOR_PRECISION,
    OID_SENSOR_SCALE,
    OID_SENSOR_TYPE,
    OID_SENSOR_VALUE,
    build_entity_sensors,
    pair_psu_power,
)
from rackpulse.collectors.power_base import PowerCollector, PowerReading
from rackpulse.config import AppConfig, DeviceConfig
from rackpulse.snmp_client import snmp_walk_column

# Cached sensor index maps per device host (stable across polls).
_sensor_cache: dict[str, list[int]] = {}
_MAX_POLL_ATTEMPTS = 3
_RETRY_BACKOFFS = (0.5, 1.0)


class AristaSwitchCollector(PowerCollector):
    device_type = "arista_switch"

    async def get_power(
        self,
        device: DeviceConfig,
        config: AppConfig,
    ) -> PowerReading:
        snmp = config.snmp
        last_error: str | None = None

        for attempt in range(_MAX_POLL_ATTEMPTS):
            try:
                sensors = await self._load_sensors(device, snmp)
                watts, volts, amps, psu_details = pair_psu_power(sensors)
                if watts <= 0:
                    raise ValueError("No active PSU voltage/current sensor pairs found")

                _sensor_cache[device.host] = [s.index for s in sensors]
                return PowerReading(
                    watts=watts,
                    volts=round(volts, 2) if volts is not None else None,
                    amps=round(amps, 2) if amps is not None else None,
                    extra={
                        "psu_count": len(psu_details),
                        "psus": psu_details,
                        "sensor_count": len(sensors),
                    },
                )
            except Exception as exc:  # noqa: BLE001
                last_error = str(exc)
                if attempt < _MAX_POLL_ATTEMPTS - 1:
                    await asyncio.sleep(_RETRY_BACKOFFS[attempt])

        raise RuntimeError(last_error or "SNMP sensor poll failed")

    async def _load_sensors(self, device: DeviceConfig, snmp) -> list:
        columns = await asyncio.gather(
            snmp_walk_column(device, OID_SENSOR_TYPE, snmp),
            snmp_walk_column(device, OID_SENSOR_SCALE, snmp),
            snmp_walk_column(device, OID_SENSOR_PRECISION, snmp),
            snmp_walk_column(device, OID_SENSOR_VALUE, snmp),
            snmp_walk_column(device, OID_SENSOR_OPER_STATUS, snmp),
            snmp_walk_column(device, OID_SENSOR_PHYSICAL_INDEX, snmp),
        )

        for result, label in zip(columns, ("type", "scale", "precision", "value", "oper", "physical"), strict=True):
            data, err = result
            if err and not data:
                raise RuntimeError(f"ENTITY-SENSOR-MIB walk failed ({label}): {err}")

        types, _ = columns[0]
        scales, _ = columns[1]
        precisions, _ = columns[2]
        values, _ = columns[3]
        oper_statuses, _ = columns[4]
        physical_indexes, _ = columns[5]

        if not types:
            raise RuntimeError("No ENTITY-SENSOR-MIB entries returned")

        return build_entity_sensors(types, scales, precisions, values, oper_statuses, physical_indexes)


SwitchCollector = AristaSwitchCollector
