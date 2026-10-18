"""Enums distinctes observees dans l'application VAV 4.14.4."""

from enum import IntEnum


class WorkingMode(IntEnum):
    """Mode global du service thermostat (`workingMode`)."""

    AUTO = 0
    COMFORT = 1
    COMFORT_MINUS_ONE = 2
    COMFORT_MINUS_TWO = 3
    ECO = 4
    FROST_PROTECTION = 5
    OFF = 6
    HOLIDAYS = 7


class PilotMode(IntEnum):
    """Ordre fil pilote (weeklyEvents.mm, holidays.mm, capability 6)."""

    OFF = 0
    COMFORT = 2
    ECO = 3
    FROST_PROTECTION = 8
    COMFORT_MINUS_ONE = 9
    COMFORT_MINUS_TWO = 10


def known_enum(enum_type: type[IntEnum], value: object) -> IntEnum | int | None:
    """Conserver les futurs codes inconnus sans casser toute la decouverte."""
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, int):
        return None
    try:
        return enum_type(value)
    except ValueError:
        return value
