from rackpulse.collectors.entity_sensor import (
    EntitySensor,
    SENSOR_OPER_OK,
    SENSOR_TYPE_AMPS,
    SENSOR_TYPE_VOLTS,
    SENSOR_TYPE_WATTS,
    pair_psu_power,
    scale_sensor_value,
)


def test_scale_sensor_acceptance_example() -> None:
    amps = scale_sensor_value(97, scale=0, precision=2)
    volts = scale_sensor_value(20850, scale=0, precision=2)
    assert amps == 0.97
    assert volts == 208.5
    assert round(volts * amps, 2) == 202.25


def test_direct_watt_sensors() -> None:
    sensors = [
        EntitySensor(1, SENSOR_TYPE_WATTS, 0, 0, 198, SENSOR_OPER_OK, 10, 198.0),
    ]
    watts, volts, amps, psus = pair_psu_power(sensors)
    assert watts == 198.0
    assert volts is None
    assert amps is None
    assert len(psus) == 1


def test_pair_psu_power_sums_redundant_psus() -> None:
    sensors = [
        EntitySensor(1, SENSOR_TYPE_VOLTS, 0, 2, 20850, SENSOR_OPER_OK, 100, 208.5),
        EntitySensor(2, SENSOR_TYPE_AMPS, 0, 2, 97, SENSOR_OPER_OK, 100, 0.97),
        EntitySensor(3, SENSOR_TYPE_VOLTS, 0, 2, 20800, SENSOR_OPER_OK, 101, 208.0),
        EntitySensor(4, SENSOR_TYPE_AMPS, 0, 2, 95, SENSOR_OPER_OK, 101, 0.95),
        EntitySensor(5, SENSOR_TYPE_VOLTS, 0, 2, 0, 4, 102, 0.0),  # non-operational
    ]
    watts, volts, amps, psus = pair_psu_power(sensors)
    assert len(psus) == 2
    assert watts == round(208.5 * 0.97 + 208.0 * 0.95, 2)
    assert volts == 208.5
    assert amps == 0.97


def test_pair_psu_power_arista_index_fallback() -> None:
    """Arista often omits operStatus/physicalIndex; pair V/A by sorted index."""
    from rackpulse.collectors.entity_sensor import build_entity_sensors

    sensors = build_entity_sensors(
        {100721104: SENSOR_TYPE_VOLTS, 100721102: SENSOR_TYPE_AMPS},
        {100721104: 0, 100721102: 0},
        {100721104: 2, 100721102: 2},
        {100721104: 20850, 100721102: 97},
        {},
        {},
    )
    watts, volts, amps, psus = pair_psu_power(sensors)
    assert watts == 202.25
    assert volts == 208.5
    assert amps == 0.97
    assert len(psus) == 1
