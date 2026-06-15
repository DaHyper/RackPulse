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
from rackpulse.config import AppConfig, DeviceConfig, SnmpDefaults
from rackpulse.snmp_client import snmp_walk_column

_sensor_cache: dict[str, list[int]] = {}
_MAX_POLL_ATTEMPTS = 3
_RETRY_BACKOFFS = (0.5, 1.0)


class EntitySensorSwitchCollector(PowerCollector):
    """Power via ENTITY-SENSOR-MIB (RFC 3433) — Arista, Cisco, Dell, and others."""

    device_type = "entity_sensor_switch"

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
                    types = sorted({s.sensor_type for s in sensors})
                    raise ValueError(
                        "No PSU power sensors matched "
                        f"(found {len(sensors)} sensors, types={types})"
                    )

                _sensor_cache[device.host] = [s.index for s in sensors]
                method = "watts" if volts is None and amps is None else "volts_amps"
                return PowerReading(
                    watts=watts,
                    volts=round(volts, 2) if volts is not None else None,
                    amps=round(amps, 2) if amps is not None else None,
                    extra={
                        "method": method,
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

    async def _load_sensors(self, device: DeviceConfig, snmp: SnmpDefaults) -> list:
        # Walk columns sequentially — some switches drop concurrent SNMP requests.
        types, type_err = await snmp_walk_column(device, OID_SENSOR_TYPE, snmp)
        if type_err and not types:
            raise RuntimeError(f"ENTITY-SENSOR-MIB walk failed (type): {type_err}")

        scales, _ = await snmp_walk_column(device, OID_SENSOR_SCALE, snmp)
        precisions, _ = await snmp_walk_column(device, OID_SENSOR_PRECISION, snmp)
        values, value_err = await snmp_walk_column(device, OID_SENSOR_VALUE, snmp)
        if value_err and not values:
            raise RuntimeError(f"ENTITY-SENSOR-MIB walk failed (value): {value_err}")

        oper_statuses, _ = await snmp_walk_column(device, OID_SENSOR_OPER_STATUS, snmp)
        physical_indexes, _ = await snmp_walk_column(device, OID_SENSOR_PHYSICAL_INDEX, snmp)

        if not types or not values:
            raise RuntimeError("No ENTITY-SENSOR-MIB entries returned")

        return build_entity_sensors(types, scales, precisions, values, oper_statuses, physical_indexes)
