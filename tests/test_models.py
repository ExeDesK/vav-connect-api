from datetime import datetime, timedelta, timezone

from vav_connect import Device, PilotMode, SessionTokens, Thermostat, WorkingMode
from vav_connect.models import Home, Room, Snapshot, Hub


def _sensor() -> Device:
    return Device.from_api(
        {
            "_id": 11,
            "roomId": "room-a",
            "name": "Capteur Salon",
            "model": "VAV-256215-SND1",
            "properties": {"keyList": [{"v": "SECRET_NEVER_IN_MODEL"}]},
            "temp": [{"properties": {"keyList": [{"v": "SECRET_NEVER_IN_MODEL"}]}}],
            "endpoints": [
                {
                    "index": 0,
                    "capabilities": [
                        {"_id": 4, "value": 2973, "unit": "Kelvin"},
                        {"_id": 15, "value": 50.93, "unit": "%"},
                        {"_id": 20, "value": 100, "unit": "%"},
                        {"_id": 31, "value": 0},
                        {"_id": 999, "value": "SECRET_NEVER_IN_MODEL"},
                    ],
                },
            ],
        },
    )


def _module() -> Device:
    return Device.from_api(
        {
            "_id": 12,
            "name": "Module Salon",
            "endpoints": [{"index": 0, "capabilities": [
                {"_id": 6, "value": 0},
                {"_id": 23, "value": 0, "unit": "W"},
                {"_id": 18, "value": 0.2, "unit": "kWh"},
            ]}],
        },
    )


def _thermostat() -> Thermostat:
    return Thermostat.from_api(
        {
            "_id": 42,
            "hubId": "hub-a",
            "roomId": "room-a",
            "type": "thermostat",
            "workingMode": 7,
            "comfortTemp": 20,
            "holidays": {"until": "2026-10-31T12:56:00.000Z", "mm": 8},
            "weeklyEvents": [
                {"d": 0, "t": 0, "mm": 3},
                {"d": 1, "t": 1800, "mm": 2},
            ],
            "sensors": {"temp": {"deviceId": 11, "endpointIndex": 0, "capabilityId": 4}},
            "modules": [{"deviceId": 12, "endpointIndex": 0, "capabilityId": 6}],
            "loadShedding": False,
        },
    )


def test_sensor_projection_and_temperature() -> None:
    sensor = _sensor()
    assert sensor.temperature_c == 24.15
    assert sensor.humidity_pct == 50.93
    assert sensor.battery_pct == 100
    assert sensor.reachable is False
    assert sensor.capability(999) is None
    assert "SECRET_NEVER_IN_MODEL" not in repr(sensor)
    assert "keyList" not in repr(sensor)


def test_modes_holidays_and_weekday_offsets() -> None:
    thermostat = _thermostat()
    assert thermostat.working_mode == WorkingMode.HOLIDAYS
    assert thermostat.holidays is not None
    assert thermostat.holidays.pilot_mode == PilotMode.FROST_PROTECTION
    assert thermostat.holidays.until == datetime(2026, 10, 31, 12, 56, tzinfo=timezone.utc)
    assert thermostat.weekly_events[1].day_index == 1
    assert thermostat.weekly_events[1].minute_of_day == 360
    assert thermostat.weekly_events[0].pilot_mode == PilotMode.ECO
    assert thermostat.load_shedding_flag_unclassified is False
    assert Thermostat.from_api({"_id": 43, "workingMode": 0}).holidays is None
    assert Thermostat.from_api({"_id": 43, "workingMode": 42}).working_mode == 42


def test_zone_join_and_unknown_energy_semantics() -> None:
    zone = Snapshot.from_parts(
        Home("home-a", True, True, False),
        (Hub("hub-a", "Boite", 1),),
        (Room("room-a", "Salon", False, None),),
        (_sensor(), _module()),
        (_thermostat(),),
    ).zones[0]
    assert zone.name == "Salon"
    assert zone.temperature_c == 24.15
    assert zone.pilot_mode == PilotMode.OFF
    assert zone.module.power_w == 0
    assert zone.module.energy_kwh_unclassified == 0.2


def test_token_repr_and_expiration() -> None:
    tokens = SessionTokens("ACCESS_SECRET", "REFRESH_SECRET", datetime.now(timezone.utc) + timedelta(seconds=5))
    assert tokens.expires_soon()
    assert "ACCESS_SECRET" not in repr(tokens)
    assert "REFRESH_SECRET" not in repr(tokens)
