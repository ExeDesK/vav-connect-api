"""Modeles de lecture VAV.

La conversion ne conserve volontairement ni `properties` (cle Zigbee possible),
ni `temp` de l'objet appareil, ni secrets de la passerelle, ni metadonnees du
logement inutiles (PDL, adresse, nom de l'installateur, etc.).
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from datetime import datetime
from typing import Any

from .enums import PilotMode, WorkingMode, known_enum

# Capacites non sensibles et deja observees. Ne jamais retourner les autres
# valeurs arbitraires dans les modeles publics (elles peuvent etre des secrets).
_SAFE_CAPABILITIES = frozenset({1, 4, 6, 15, 18, 20, 23, 31, 168, 169})
_RADIATOR_POWER_W = {0: 700, 1: 1000, 2: 1500, 3: 2000, 4: 2500}


def _identifier(value: object) -> str | None:
    # Ne jamais transformer un objet/dictionnaire imprevu (possible secret)
    # en chaine publique a l'insu de l'appelant.
    return str(value) if isinstance(value, str) or type(value) is int else None


def _label(value: object, fallback: str) -> str:
    return value if isinstance(value, str) and value else fallback


def _num(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        result = float(value)
    except OverflowError:
        return None
    return result if math.isfinite(result) else None


def _date(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


@dataclass(frozen=True, slots=True)
class Home:
    id: str
    is_at_home: bool | None
    is_activated: bool | None
    is_suspended: bool | None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> Home:
        return cls(
            id=_identifier(raw.get("_id")) or "",
            is_at_home=_bool_or_none(raw.get("isAtHome")),
            is_activated=_bool_or_none(raw.get("isActivated")),
            is_suspended=_bool_or_none(raw.get("isSuspended")),
        )


@dataclass(frozen=True, slots=True)
class Hub:
    id: str
    label: str
    state: int | None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> Hub:
        state = raw.get("state")
        return cls(
            id=_identifier(raw.get("_id")) or "",
            label=_label(raw.get("label"), "Passerelle VAV"),
            state=state if isinstance(state, int) and not isinstance(state, bool) else None,
        )


@dataclass(frozen=True, slots=True)
class Room:
    id: str
    name: str
    is_read_only: bool
    service_id: str | None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> Room:
        return cls(
            id=_identifier(raw.get("_id")) or "",
            name=_label(raw.get("name"), "Piece sans nom"),
            is_read_only=raw.get("isReadOnly") is True,
            service_id=_identifier(raw.get("serviceId")),
        )


@dataclass(frozen=True, slots=True)
class Capability:
    id: int
    endpoint_index: int
    value: int | float | str | None
    unit: str | None


@dataclass(frozen=True, slots=True)
class Device:
    id: str
    name: str
    model: str
    room_id: str | None
    hub_id: str | None
    capabilities: tuple[Capability, ...]

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> Device:
        capabilities: list[Capability] = []
        for endpoint in raw.get("endpoints") or []:
            if not isinstance(endpoint, dict):
                continue
            index = endpoint.get("index", 0)
            if not isinstance(index, int) or isinstance(index, bool):
                continue
            for capability in endpoint.get("capabilities") or []:
                if not isinstance(capability, dict):
                    continue
                cap_id = capability.get("_id")
                if not isinstance(cap_id, int) or isinstance(cap_id, bool) or cap_id not in _SAFE_CAPABILITIES:
                    continue
                value = capability.get("value")
                # Refuser les valeurs composites et les bools dans la projection.
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    value = None
                elif _num(value) is None:
                    value = None
                capabilities.append(
                    Capability(
                        id=cap_id,
                        endpoint_index=index,
                        value=value,
                        unit=capability.get("unit") if capability.get("unit") in ("Kelvin", "%", "W", "kWh") else None,
                    )
                )
        return cls(
            id=_identifier(raw.get("_id")) or "",
            name=_label(raw.get("name") or raw.get("label"), "Appareil sans nom"),
            model=_label(raw.get("model"), ""),
            room_id=_identifier(raw.get("roomId")),
            hub_id=_identifier(raw.get("hubId")),
            capabilities=tuple(capabilities),
        )

    def capability(self, capability_id: int, *, endpoint_index: int = 0) -> Capability | None:
        return next(
            (cap for cap in self.capabilities if cap.id == capability_id and cap.endpoint_index == endpoint_index),
            None,
        )

    @property
    def temperature_c(self) -> float | None:
        """Capacite 4: Kelvin x10, d'apres les captures VAV 4.14.4."""
        cap = self.capability(4)
        value = _num(cap.value) if cap else None
        if value is None or cap is None or cap.unit != "Kelvin":
            return None
        return round(value / 10 - 273.15, 2)

    @property
    def humidity_pct(self) -> float | None:
        cap = self.capability(15)
        return _num(cap.value) if cap else None

    @property
    def battery_pct(self) -> float | None:
        cap = self.capability(20)
        return _num(cap.value) if cap else None

    @property
    def power_w(self) -> float | None:
        cap = self.capability(23)
        return _num(cap.value) if cap else None

    @property
    def rated_radiator_power_w(self) -> int | None:
        """Capacite 169 : selection 0..4 de puissance nominale en watts."""
        cap = self.capability(169)
        if cap is None or type(cap.value) is not int:
            return None
        return _RADIATOR_POWER_W.get(cap.value)

    @property
    def radiator_type_code(self) -> int | None:
        """Code bruite de type de radiateur, sans deduire une description."""
        cap = self.capability(168)
        return cap.value if cap is not None and type(cap.value) is int else None

    @property
    def supply_on(self) -> bool | None:
        """Capacite 1 : etat electrique reporte; distinct du mode thermostat."""
        cap = self.capability(1)
        return cap.value == 1 if cap and cap.value in (0, 1) else None

    @property
    def energy_kwh_unclassified(self) -> float | None:
        """Capacite 18: unite kWh, cumul/periode NON determines."""
        cap = self.capability(18)
        return _num(cap.value) if cap else None

    @property
    def reachable(self) -> bool | None:
        cap = self.capability(31)
        if cap is None or cap.value not in (0, 1):
            return None
        return cap.value == 1


@dataclass(frozen=True, slots=True)
class DeviceReference:
    device_id: str
    endpoint_index: int
    capability_id: int

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> DeviceReference:
        return cls(
            device_id=_identifier(raw.get("deviceId")) or "",
            endpoint_index=raw.get("endpointIndex") if type(raw.get("endpointIndex")) is int else 0,
            capability_id=raw.get("capabilityId") if type(raw.get("capabilityId")) is int else -1,
        )


@dataclass(frozen=True, slots=True)
class WeekEvent:
    day_index: int
    minute_of_week: int
    pilot_mode: PilotMode | int | None

    @property
    def minute_of_day(self) -> int:
        return self.minute_of_week - 1440 * self.day_index

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> WeekEvent:
        day = raw.get("d")
        minute = raw.get("t")
        if type(day) is not int or not 0 <= day <= 6 or type(minute) is not int \
                or not 1440 * day <= minute < 1440 * (day + 1):
            raise ValueError("Evenement hebdomadaire invalide")
        return cls(
            day_index=day,
            minute_of_week=minute,
            pilot_mode=known_enum(PilotMode, raw.get("mm")),
        )


@dataclass(frozen=True, slots=True)
class Holidays:
    until: datetime | None
    pilot_mode: PilotMode | int | None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> Holidays:
        return cls(until=_date(raw.get("until")), pilot_mode=known_enum(PilotMode, raw.get("mm")))


@dataclass(frozen=True, slots=True)
class Thermostat:
    id: str
    hub_id: str | None
    room_id: str | None
    working_mode: WorkingMode | int | None
    comfort_temperature_c: float | None
    holidays: Holidays | None
    weekly_events: tuple[WeekEvent, ...]
    sensor: DeviceReference | None
    modules: tuple[DeviceReference, ...]
    load_shedding_flag_unclassified: bool | None
    updated_at: datetime | None

    @classmethod
    def from_api(cls, raw: dict[str, Any]) -> Thermostat:
        sensors = raw.get("sensors") or {}
        temp_ref = sensors.get("temp") if isinstance(sensors, dict) else None
        holiday = raw.get("holidays")
        return cls(
            id=_identifier(raw.get("_id")) or "",
            hub_id=_identifier(raw.get("hubId")),
            room_id=_identifier(raw.get("roomId")),
            working_mode=known_enum(WorkingMode, raw.get("workingMode")),
            comfort_temperature_c=_num(raw.get("comfortTemp")),
            holidays=Holidays.from_api(holiday) if isinstance(holiday, dict) else None,
            weekly_events=_read_week_events(raw.get("weeklyEvents")),
            sensor=DeviceReference.from_api(temp_ref) if isinstance(temp_ref, dict) else None,
            modules=tuple(
                DeviceReference.from_api(module)
                for module in raw.get("modules") or []
                if isinstance(module, dict)
            ),
            load_shedding_flag_unclassified=_bool_or_none(raw.get("loadShedding")),
            updated_at=_date(raw.get("updatedAt")),
        )


    @property
    def is_holiday_mode(self) -> bool:
        return self.working_mode == WorkingMode.HOLIDAYS

    @property
    def holiday_until(self) -> datetime | None:
        return self.holidays.until if self.holidays else None

    @property
    def holiday_pilot_mode(self) -> PilotMode | int | None:
        return self.holidays.pilot_mode if self.holidays else None

    def events_for_day(self, day_index: int) -> tuple[WeekEvent, ...]:
        """Transitions du jour d=0..6, en minutes absolues de la semaine."""
        if type(day_index) is not int or not 0 <= day_index <= 6:
            raise ValueError("day_index doit etre compris entre 0 et 6")
        return tuple(sorted(
            (event for event in self.weekly_events if event.day_index == day_index),
            key=lambda event: event.minute_of_week,
        ))


@dataclass(frozen=True, slots=True)
class ZoneReading:
    thermostat_id: str
    name: str
    thermostat: Thermostat
    sensor: Device | None
    module: Device | None

    @property
    def temperature_c(self) -> float | None:
        if self.sensor is None or self.thermostat.sensor is None:
            return None
        ref = self.thermostat.sensor
        cap = self.sensor.capability(ref.capability_id, endpoint_index=ref.endpoint_index)
        if cap is None or cap.unit != "Kelvin":
            return None
        val = _num(cap.value)
        return round(val / 10 - 273.15, 2) if val is not None else None

    @property
    def comfort_temperature_c(self) -> float | None:
        return self.thermostat.comfort_temperature_c

    @property
    def working_mode(self) -> WorkingMode | int | None:
        return self.thermostat.working_mode

    @property
    def humidity_pct(self) -> float | None:
        return self.sensor.humidity_pct if self.sensor else None

    @property
    def battery_pct(self) -> float | None:
        return self.sensor.battery_pct if self.sensor else None

    @property
    def sensor_reachable(self) -> bool | None:
        return self.sensor.reachable if self.sensor else None

    @property
    def module_reachable(self) -> bool | None:
        return self.module.reachable if self.module else None

    @property
    def power_w(self) -> float | None:
        return self.module.power_w if self.module else None

    @property
    def pilot_mode(self) -> PilotMode | int | None:
        if self.module is None or not self.thermostat.modules:
            return None
        ref = self.thermostat.modules[0]
        cap = self.module.capability(ref.capability_id, endpoint_index=ref.endpoint_index)
        return known_enum(PilotMode, cap.value) if cap else None


@dataclass(frozen=True, slots=True)
class Snapshot:
    home: Home
    hubs: tuple[Hub, ...]
    rooms: tuple[Room, ...]
    devices: tuple[Device, ...]
    thermostats: tuple[Thermostat, ...]
    zones: tuple[ZoneReading, ...]

    @classmethod
    def from_parts(
        cls,
        home: Home,
        hubs: tuple[Hub, ...],
        rooms: tuple[Room, ...],
        devices: tuple[Device, ...],
        thermostats: tuple[Thermostat, ...],
    ) -> Snapshot:
        by_room = {room.id: room for room in rooms}
        by_device = {device.id: device for device in devices}
        zones = []
        for thermostat in thermostats:
            sensor = by_device.get(thermostat.sensor.device_id) if thermostat.sensor else None
            module = by_device.get(thermostat.modules[0].device_id) if thermostat.modules else None
            room = by_room.get(thermostat.room_id) if thermostat.room_id else None
            name = room.name if room else (sensor.name if sensor else f"Thermostat {thermostat.id}")
            zones.append(ZoneReading(thermostat.id, name, thermostat, sensor, module))
        return cls(home, hubs, rooms, devices, thermostats, tuple(zones))


def _read_week_events(value: object) -> tuple[WeekEvent, ...]:
    """Ignorer les evenements corrompus sans perdre la lecture de la zone."""
    if not isinstance(value, list):
        return ()
    valid: list[WeekEvent] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        try:
            valid.append(WeekEvent.from_api(item))
        except (ValueError, TypeError, KeyError):
            continue
    return tuple(valid)


def _bool_or_none(value: object) -> bool | None:
    return value if isinstance(value, bool) else None
