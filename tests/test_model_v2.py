"""Projections de capteurs et programmation, donnees exclusivement synthetiques."""

from datetime import datetime, timezone
import math

import pytest

from vav_connect import Device, PilotMode, Thermostat, WorkingMode
from vav_connect.models import WeekEvent, ZoneReading


def test_safe_device_radiator_fields() -> None:
    device = Device.from_api({
        "_id": "module-x", "aesKey": "NEVER_STORE_A_KEY",
        "endpoints": [{"index": 0, "capabilities": [
            {"_id": 1, "value": 1}, {"_id": 169, "value": 1},
            {"_id": 168, "value": 3}, {"_id": 23, "value": 230.5, "unit": "W"},
        ]}],
    })
    assert device.rated_radiator_power_w == 1000
    assert device.radiator_type_code == 3
    assert device.supply_on is True
    assert device.power_w == 230.5
    assert "NEVER_STORE_A_KEY" not in repr(device)


def test_invalid_numeric_values_are_not_exposed() -> None:
    for invalid in [math.inf, -math.inf, math.nan, True, "secret"]:
        device = Device.from_api({"_id": "a", "endpoints": [{"index": 0, "capabilities": [
            {"_id": 23, "value": invalid},
        ]}]})
        assert device.power_w is None


def test_schedule_helpers_sort_and_skip_invalid_events() -> None:
    therm = Thermostat.from_api({
        "_id": "42", "workingMode": 7, "comfortTemp": 21,
        "holidays": {"until": "2026-10-31T12:56:00Z", "mm": 0},
        "weeklyEvents": [
            {"d": 0, "t": 180, "mm": 3},
            {"d": 1, "t": 1800, "mm": 2},
            {"d": 0, "t": 0, "mm": 0},
            {"d": 7, "t": 10080, "mm": 2},  # Hors semaine
            {"d": 0, "t": -1, "mm": 2},
            {"d": 1, "t": 3, "mm": 2},  # t incoherent avec d
            {"d": "0", "t": 42, "mm": 2},
            None,
        ],
    })
    assert therm.is_holiday_mode
    assert therm.holiday_until == datetime(2026, 10, 31, 12, 56, tzinfo=timezone.utc)
    assert therm.holiday_pilot_mode == PilotMode.OFF
    assert [(e.minute_of_week, e.pilot_mode) for e in therm.events_for_day(0)] == [
        (0, PilotMode.OFF), (180, PilotMode.ECO),
    ]
    assert len(therm.weekly_events) == 3
    with pytest.raises(ValueError):
        therm.events_for_day(7)
    with pytest.raises(ValueError):
        therm.events_for_day(True)


def test_week_event_validation_and_unknown_future_modes() -> None:
    assert WeekEvent.from_api({"d": 6, "t": 10079, "mm": 444}).pilot_mode == 444
    with pytest.raises(ValueError):
        WeekEvent.from_api({"d": 0, "t": 1440, "mm": 2})
    assert Thermostat.from_api({"_id": "42", "workingMode": 999}).working_mode == 999


def test_untrusted_composite_fields_never_appear_in_models() -> None:
    private = {"secret": "PRIVATE_NESTED_SECRET"}
    device = Device.from_api({
        "_id": private, "name": private, "model": private, "roomId": private,
        "endpoints": [{"index": 0, "capabilities": [
            {"_id": 23, "value": 0, "unit": "PRIVATE_NESTED_SECRET"},
        ]}],
    })
    assert device.id == ""
    assert device.name == "Appareil sans nom"
    assert device.room_id is None
    assert "PRIVATE_NESTED_SECRET" not in repr(device)


def test_extremely_large_numbers_cannot_crash_device_projection() -> None:
    device = Device.from_api({"_id": "id", "endpoints": [
        {"index": 0, "capabilities": [{"_id": 23, "value": 10 ** 10000}]},
    ]})
    assert device.power_w is None
