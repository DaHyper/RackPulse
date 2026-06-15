from __future__ import annotations

from dataclasses import dataclass

# ENTITY-SENSOR-MIB (RFC 3433) — 1.3.6.1.2.1.99.1.1.1
ENTITY_SENSOR_BASE = "1.3.6.1.2.1.99.1.1.1"
OID_SENSOR_TYPE = f"{ENTITY_SENSOR_BASE}.1"
OID_SENSOR_SCALE = f"{ENTITY_SENSOR_BASE}.2"
OID_SENSOR_PRECISION = f"{ENTITY_SENSOR_BASE}.3"
OID_SENSOR_VALUE = f"{ENTITY_SENSOR_BASE}.4"
OID_SENSOR_OPER_STATUS = f"{ENTITY_SENSOR_BASE}.5"
OID_SENSOR_PHYSICAL_INDEX = f"{ENTITY_SENSOR_BASE}.9"

# entPhySensorType values
SENSOR_TYPE_VOLTS = 3
SENSOR_TYPE_AMPS = 5
SENSOR_TYPE_CELSIUS = 8
SENSOR_TYPE_RPM = 10

# entPhySensorOperStatus
SENSOR_OPER_OK = 2


@dataclass
class EntitySensor:
    index: int
    sensor_type: int
    scale: int
    precision: int
    raw_value: float
    oper_status: int
    physical_index: int
    scaled_value: float


def scale_sensor_value(raw: float, scale: int, precision: int) -> float:
    """Apply RFC3433 ENTITY-SENSOR-MIB scaling."""
    return float(raw) * (10**scale) / (10**precision)


def build_entity_sensors(
    types: dict[int, float],
    scales: dict[int, float],
    precisions: dict[int, float],
    values: dict[int, float],
    oper_statuses: dict[int, float],
    physical_indexes: dict[int, float],
) -> list[EntitySensor]:
    sensors: list[EntitySensor] = []
    for index in sorted(types.keys()):
        if index not in values:
            continue
        scale = int(scales.get(index, 0))
        precision = int(precisions.get(index, 0))
        raw = values[index]
        sensors.append(
            EntitySensor(
                index=index,
                sensor_type=int(types[index]),
                scale=scale,
                precision=precision,
                raw_value=raw,
                oper_status=int(oper_statuses.get(index, 0)),
                physical_index=int(physical_indexes.get(index, 0)),
                scaled_value=scale_sensor_value(raw, scale, precision),
            )
        )
    return sensors


def pair_psu_power(sensors: list[EntitySensor]) -> tuple[float, float | None, float | None, list[dict]]:
    """Pair voltage/current sensors by physical entity and sum PSU watts."""
    active = [s for s in sensors if s.oper_status == SENSOR_OPER_OK]
    by_entity: dict[int, dict[str, EntitySensor]] = {}

    for sensor in active:
        if sensor.sensor_type not in (SENSOR_TYPE_VOLTS, SENSOR_TYPE_AMPS):
            continue
        entity = sensor.physical_index or sensor.index
        bucket = by_entity.setdefault(entity, {})
        if sensor.sensor_type == SENSOR_TYPE_VOLTS:
            bucket["volts"] = sensor
        else:
            bucket["amps"] = sensor

    psu_readings: list[dict] = []
    total_watts = 0.0
    primary_volts: float | None = None
    primary_amps: float | None = None

    for entity, pair in sorted(by_entity.items()):
        volt = pair.get("volts")
        amp = pair.get("amps")
        if volt is None or amp is None:
            continue
        watts = round(volt.scaled_value * amp.scaled_value, 2)
        if watts <= 0:
            continue
        total_watts += watts
        psu_readings.append(
            {
                "entity": entity,
                "volts": round(volt.scaled_value, 2),
                "amps": round(amp.scaled_value, 2),
                "watts": watts,
            }
        )
        if primary_volts is None:
            primary_volts = volt.scaled_value
            primary_amps = amp.scaled_value

    if psu_readings:
        return round(total_watts, 2), primary_volts, primary_amps, psu_readings

    # Fallback: single system-level V/I pair when physical index grouping fails
    volts = [s for s in active if s.sensor_type == SENSOR_TYPE_VOLTS]
    amps = [s for s in active if s.sensor_type == SENSOR_TYPE_AMPS]
    if len(volts) == 1 and len(amps) == 1:
        v = volts[0].scaled_value
        a = amps[0].scaled_value
        watts = round(v * a, 2)
        return (
            watts,
            v,
            a,
            [{"entity": 0, "volts": round(v, 2), "amps": round(a, 2), "watts": watts}],
        )

    return 0.0, None, None, []
