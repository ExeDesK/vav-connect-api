"""Explicitly opted-in VAV thermostat controls.

All control calls are PREVIEWS unless ``apply=True``.  Even with apply=True,
VAVClient(allow_writes=True) is mandatory.  No writes are retried, and
read-after-write verification is required.  Global operations are NOT atomic.

The cloud may have more load-shedding state than the `loadShedding` field
exposes.  Callers must separately check for active grid interventions; this
module cannot guarantee that writes are safe during demand-response events.
"""

from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import math
import re
from typing import TYPE_CHECKING, Any, Mapping, Sequence
from urllib.parse import quote

from .enums import PilotMode, WorkingMode
from .exceptions import ControlError, PartialWriteError, WriteUncertainError
from .models import WeekEvent

if TYPE_CHECKING:
    from .client import VAVClient

_VALID_MODES = set(WorkingMode)
_VALID_PILOT = set(PilotMode)
_ALLOWED_HOLIDAY = {PilotMode.OFF, PilotMode.ECO, PilotMode.FROST_PROTECTION}
_REQUIRED = frozenset({
    "_id", "hubId", "type", "isActive", "workingMode", "weeklyEvents",
    "comfortTemp", "loadShedding", "updatedAt", "modules", "sensors",
})
_INVARIANTS = frozenset({
    "learning", "modules", "sensors", "weeklyEvents", "comfortTemp",
    "loadShedding", "hysteresis", "limitTemp", "enableReports", "version",
    "holidays", "workingMode",
})


@dataclass(frozen=True, slots=True)
class ControlChange:
    """Safe display of a planned change, without raw gateway JSON."""

    target: str  # thermostat service id, or 'home'
    field: str
    before: int | float | bool | str | None
    after: int | float | bool | str | None


@dataclass(frozen=True, slots=True)
class ControlResult:
    operation: str
    changes: tuple[ControlChange, ...]
    applied: bool
    mutations: int

    @property
    def needs_changes(self) -> bool:
        return bool(self.changes)


@dataclass(slots=True)
class _PlannedThermostat:
    thermostat_id: str
    hub_id: str
    before: dict[str, Any]
    after: dict[str, Any]
    permitted: frozenset[str]

    @property
    def changed(self) -> bool:
        return self.before != self.after


class VAVControl:
    """Write facade. Public methods never expose the complete gateway payload."""

    def __init__(self, client: VAVClient) -> None:
        self._client = client

    async def set_working_mode(
        self, thermostat_id: str, mode: WorkingMode, *, apply: bool = False,
    ) -> ControlResult:
        if not isinstance(mode, WorkingMode) or mode == WorkingMode.HOLIDAYS:
            raise ValueError("Utiliser un WorkingMode hors Vacances (0..6)")
        return await self._single(
            thermostat_id, "working_mode", {"workingMode": int(mode)}, apply=apply,
            require_not_holidays=True,
        )

    async def set_comfort_temperature(
        self, thermostat_id: str, temperature_c: float, *, apply: bool = False,
    ) -> ControlResult:
        if isinstance(temperature_c, bool) or not isinstance(temperature_c, (int, float)) \
                or not math.isfinite(temperature_c) or not 16 <= temperature_c <= 28 \
                or temperature_c * 2 != round(temperature_c * 2):
            raise ValueError("Temperature Confort : 16..28 C, par pas de 0.5")
        return await self._single(
            thermostat_id, "comfort_temperature", {"comfortTemp": float(temperature_c)},
            apply=apply, require_not_holidays=True,
        )

    async def set_weekly_schedule(
        self, thermostat_id: str, events: Sequence[WeekEvent], *, apply: bool = False,
    ) -> ControlResult:
        compiled = _validate_schedule(events)
        return await self._single(
            thermostat_id, "weekly_schedule", {"weeklyEvents": compiled},
            apply=apply, require_auto=True,
        )

    async def replace_schedule_days(
        self, thermostat_id: str, days: Mapping[int, Sequence[WeekEvent]], *, apply: bool = False,
    ) -> ControlResult:
        if not isinstance(days, Mapping) or not days:
            raise ValueError("Fournir au moins un jour a remplacer")
        new_per_day: dict[int, list[dict[str, int]]] = {}
        for day, events in days.items():
            if type(day) is not int or not 0 <= day <= 6:
                raise ValueError("Jours attendus : 0=lundi ... 6=dimanche")
            compiled = _validate_schedule(events)
            if any(event["d"] != day for event in compiled):
                raise ValueError("Un evenement ne correspond pas a son jour")
            new_per_day[day] = compiled
        # Snapshot of raw schedule is built INSIDE the execution lock below.
        return await self._single(
            thermostat_id, "weekly_schedule", {"_schedule_days": new_per_day},
            apply=apply, require_auto=True,
        )

    async def set_presence(self, is_at_home: bool, *, apply: bool = False) -> ControlResult:
        if type(is_at_home) is not bool:
            raise ValueError("is_at_home doit etre un booleen")
        return await self._global(
            "presence" if is_at_home else "absence", target_home=is_at_home,
            target_mode=WorkingMode.AUTO if is_at_home else WorkingMode.ECO,
            apply=apply,
        )

    async def set_holidays(
        self, *, until: datetime, pilot_mode: PilotMode, apply: bool = False,
    ) -> ControlResult:
        if not isinstance(pilot_mode, PilotMode) or pilot_mode not in _ALLOWED_HOLIDAY:
            raise ValueError("Vacances : choisir PilotMode.ECO, FROST_PROTECTION ou OFF")
        if not isinstance(until, datetime) or until.tzinfo is None or until.utcoffset() is None:
            raise ValueError("Date de retour avec fuseau horaire obligatoire")
        utc = until.astimezone(timezone.utc)
        if utc <= datetime.now(timezone.utc) + timedelta(minutes=10):
            raise ValueError("Date de retour trop proche ou pas dans le futur")
        iso = utc.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        return await self._global(
            "holidays", target_home=None, target_mode=WorkingMode.HOLIDAYS,
            holiday={"until": iso, "mm": int(pilot_mode)}, apply=apply,
        )

    async def cancel_holidays(self, *, apply: bool = False) -> ControlResult:
        # Application officielle: reset to Auto and force home=True.  Old
        # holidays metadata may remain stored even after cancellation.
        return await self._global(
            "cancel_holidays", target_home=True, target_mode=WorkingMode.AUTO,
            apply=apply,
        )

    async def _single(
        self, thermostat_id: str, operation: str, update: dict[str, Any], *,
        apply: bool, require_not_holidays: bool = False, require_auto: bool = False,
    ) -> ControlResult:
        _check_id(thermostat_id)
        _check_apply(apply)
        async with self._client._write_lock:
            self._allow_if_applying(apply)
            home, targets = await self._load_targets()
            target = self._find_target(targets, thermostat_id)
            previous_mode = target.before["workingMode"]
            if (require_not_holidays and previous_mode == int(WorkingMode.HOLIDAYS)) \
                    or (require_auto and previous_mode != int(WorkingMode.AUTO)):
                raise ControlError("Mode du thermostat incompatible avec cette operation")
            if "_schedule_days" in update:
                before_events = _validate_schedule_raw(target.before["weeklyEvents"])
                patches = update["_schedule_days"]
                after_events = [e for e in before_events if e["d"] not in patches]
                for replacement in patches.values():
                    after_events.extend(deepcopy(replacement))
                after_events.sort(key=lambda e: e["t"])
                _validate_schedule_raw(after_events)
                update = {"weeklyEvents": after_events}
            _merge_allowed(target, update)
            before = target.before
            changes = tuple(
                change
                for field, after in update.items()
                for change in _summarize_changes(target.thermostat_id, field, before.get(field), after)
            )
            result = ControlResult(operation, changes, applied=apply, mutations=0)
            if not apply or not target.changed:
                return result
            await self._confirm_unchanged(target)
            await self._client._send_thermostat_put(target)
            await self._verify(target)
            return ControlResult(operation, changes, applied=True, mutations=1)

    async def _global(
        self, operation: str, *, target_home: bool | None,
        target_mode: WorkingMode, holiday: dict[str, Any] | None = None,
        apply: bool,
    ) -> ControlResult:
        _check_apply(apply)
        async with self._client._write_lock:
            self._allow_if_applying(apply)
            home, targets = await self._load_targets()
            changes: list[ControlChange] = []
            target_home_id = home["_id"]
            if target_home is not None and home["isAtHome"] != target_home:
                changes.append(ControlChange("home", "isAtHome", home["isAtHome"], target_home))
            for target in targets:
                mode = target.before["workingMode"]
                if operation == "cancel_holidays":
                    if mode not in (0, 7):
                        raise ControlError("Annulation Vacances : mode non Auto/Vacances, intervention manuelle necessaire")
                    if mode == 0:
                        continue  # resume partial; do not write holidays metadata
                    update = {"workingMode": 0}
                    # Official app omits `holidays` when cancelling. Cloud may
                    # keep the previous metadata; do not require its deletion.
                    target.after.pop("holidays", None)
                    target.permitted = frozenset({"workingMode", "holidays"})
                elif operation == "holidays":
                    if mode == int(WorkingMode.HOLIDAYS):
                        raise ControlError("Deja en Vacances : annuler avant de reprogrammer")
                    update = {"workingMode": int(target_mode), "holidays": deepcopy(holiday)}
                else:
                    if mode == int(WorkingMode.HOLIDAYS):
                        raise ControlError("Vacances actives : utiliser cancel_holidays")
                    update = {"workingMode": int(target_mode)}
                _merge_allowed(target, update, check_diff=(operation != "cancel_holidays"))
                for field, value in update.items():
                    changes.extend(_summarize_changes(
                        target.thermostat_id, field, target.before.get(field), value
                    ))
            result = ControlResult(operation, tuple(changes), applied=apply, mutations=0)
            if not apply or not changes:
                return result
            completed: list[str] = []
            active_target = "home"
            try:
                # Preflight EVERY thermostat before the first mutation.
                # Cannot enforce a transaction across separate cloud requests.
                if await self._read_home() != home:
                    raise ControlError("Logement modifie pendant le precontrole")
                for item in targets:
                    await self._confirm_unchanged(item)
                if target_home is not None and home["isAtHome"] != target_home:
                    active_target = "home"
                    await self._client._send_home_patch(target_home_id, target_home)
                    if (await self._read_home())["isAtHome"] != target_home:
                        raise WriteUncertainError("PATCH accepte, presence non confirmee")
                    completed.append("home")
                for item in targets:
                    if not item.changed:
                        continue
                    active_target = item.thermostat_id
                    await self._confirm_unchanged(item)
                    await self._client._send_thermostat_put(item)
                    await self._verify(item)
                    completed.append(item.thermostat_id)
                return ControlResult(operation, tuple(changes), applied=True, mutations=len(completed))
            except Exception as exc:
                if completed or isinstance(exc, WriteUncertainError) or active_target != "home":
                    raise PartialWriteError(operation, completed=tuple(completed),
                                            uncertain_target=active_target) from None
                raise

    def _allow_if_applying(self, apply: bool) -> None:
        if apply and self._client.allow_writes is not True:
            raise ControlError("Ecritures desactivees : VAVClient(allow_writes=True) requis")

    async def _read_home(self) -> dict[str, Any]:
        data = await self._client._get("/homes")
        if not isinstance(data, dict) or type(data.get("isAtHome")) is not bool \
                or data.get("isActivated") is not True or data.get("isSuspended") is not False \
                or not isinstance(data.get("_id"), str):
            raise ControlError("Logement inactif ou donnees de presence invalides")
        _check_id(data["_id"])
        if self._client.tokens and self._client.tokens.home_id \
                and self._client.tokens.home_id != data["_id"]:
            raise ControlError("homeId de la session incompatible avec le logement")
        return data

    async def _load_targets(self) -> tuple[dict[str, Any], list[_PlannedThermostat]]:
        home = await self._read_home()
        snapshot = await self._client.get_snapshot()
        if snapshot.home.id != home["_id"] or not snapshot.zones:
            raise ControlError("Liste de zones / logement incompatible")
        if len({zone.thermostat_id for zone in snapshot.zones}) != len(snapshot.zones):
            raise ControlError("Identifiant de thermostat duplique")
        targets = []
        # One GET per hub. Never expose raw objects in public data models.
        per_hub: dict[str, dict[str, dict[str, Any]]] = {}
        for zone in snapshot.zones:
            hub_id = zone.thermostat.hub_id
            if not hub_id:
                raise ControlError("Zone sans passerelle")
            _check_id(hub_id)
            if hub_id not in per_hub:
                data = await self._client._get(f"/hubs/{quote(hub_id, safe='')}/local-services")
                if not isinstance(data, list) or any(not isinstance(e, dict) for e in data):
                    raise ControlError("Reponse local-services invalide")
                entries: dict[str, dict[str, Any]] = {}
                for item in data:
                    item_id = str(item.get("_id"))
                    if item_id in entries:
                        raise ControlError("Service local duplique")
                    entries[item_id] = item
                per_hub[hub_id] = entries
            raw = per_hub[hub_id].get(zone.thermostat_id)
            if raw is None:
                raise ControlError("Service local introuvable")
            raw = _validate_raw(raw, zone.thermostat_id, hub_id)
            targets.append(_PlannedThermostat(zone.thermostat_id, hub_id, raw, deepcopy(raw), frozenset()))
        # A partial discovery must never be mistaken for a complete global
        # action: do not ignore thermostat services missing from Snapshot.
        known = {(target.hub_id, target.thermostat_id) for target in targets}
        all_thermostats = {
            (hub, service_id)
            for hub, services in per_hub.items()
            for service_id, raw in services.items()
            if raw.get("type") == "thermostat" and raw.get("isActive") is True
        }
        if known != all_thermostats:
            raise ControlError("Découverte incomplète des thermostats : écriture refusée")
        return home, targets

    def _find_target(self, targets: list[_PlannedThermostat], thermostat_id: str) -> _PlannedThermostat:
        matches = [item for item in targets if item.thermostat_id == thermostat_id]
        if len(matches) != 1:
            raise ControlError("Thermostat non trouve ou ambigu")
        return matches[0]

    async def _confirm_unchanged(self, target: _PlannedThermostat) -> None:
        fresh = await self._read_thermostat(target)
        if fresh != target.before:
            raise ControlError("Thermostat modifie par un autre acteur : relecture et planification requises")

    async def _read_thermostat(self, target: _PlannedThermostat) -> dict[str, Any]:
        data = await self._client._get(f"/hubs/{quote(target.hub_id, safe='')}/local-services")
        if not isinstance(data, list):
            raise ControlError("local-services invalide apres ecriture")
        candidates = [e for e in data if isinstance(e, dict) and str(e.get("_id")) == target.thermostat_id]
        if len(candidates) != 1:
            raise ControlError("Thermostat non retrouve apres ecriture")
        return _validate_raw(candidates[0], target.thermostat_id, target.hub_id)

    async def _verify(self, target: _PlannedThermostat) -> None:
        for attempt in range(3):
            fresh = await self._read_thermostat(target)
            if _matches_after(fresh, target):
                return
            if attempt < 2:
                await asyncio.sleep(0.3)
        raise WriteUncertainError("PUT accepte mais nouvel etat non confirme")


def _check_apply(value: bool) -> None:
    if type(value) is not bool:
        raise ValueError("apply doit etre un booleen")


def _check_id(value: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
        raise ValueError("Identifiant VAV invalide")


def _validate_raw(raw: object, service_id: str, hub_id: str) -> dict[str, Any]:
    if not isinstance(raw, dict) or not _REQUIRED.issubset(raw) \
            or str(raw.get("_id")) != service_id or raw.get("hubId") != hub_id \
            or raw.get("type") != "thermostat" or raw.get("isActive") is not True:
        raise ControlError("Donnees de thermostat incompletes ou incoherentes")
    if raw.get("loadShedding") is not False:
        raise ControlError("loadShedding non-false; refus de modifier le thermostat")
    if type(raw.get("workingMode")) is not int or raw["workingMode"] not in {int(x) for x in _VALID_MODES}:
        raise ControlError("Mode de thermostat non reconnu")
    temp = raw["comfortTemp"]
    if isinstance(temp, bool) or not isinstance(temp, (int, float)) or not math.isfinite(temp):
        raise ControlError("Confort invalide")
    if not isinstance(raw.get("updatedAt"), str):
        raise ControlError("updatedAt absent")
    _validate_schedule_raw(raw["weeklyEvents"])
    if "holidays" in raw and not isinstance(raw["holidays"], dict):
        raise ControlError("Donnees holidays non reconnues")
    return raw


def _validate_schedule(events: Sequence[WeekEvent]) -> list[dict[str, int]]:
    if isinstance(events, (str, bytes)) or not isinstance(events, Sequence) or not 1 <= len(events) <= 200:
        raise ValueError("La programmation doit contenir 1 a 200 evenements")
    compiled = []
    for event in events:
        if not isinstance(event, WeekEvent) or not isinstance(event.pilot_mode, PilotMode):
            raise ValueError("Chaque evenement doit etre un WeekEvent avec PilotMode connu")
        if type(event.day_index) is not int or type(event.minute_of_week) is not int \
                or not 0 <= event.day_index <= 6 \
                or not 1440 * event.day_index <= event.minute_of_week < 1440 * (event.day_index + 1):
            raise ValueError("Jour ou minute absolue de semaine incorrect")
        compiled.append({"d": event.day_index, "t": event.minute_of_week, "mm": int(event.pilot_mode)})
    compiled.sort(key=lambda e: e["t"])
    _validate_schedule_raw(compiled)
    return compiled


def _validate_schedule_raw(events: object) -> list[dict[str, Any]]:
    if not isinstance(events, list) or not 1 <= len(events) <= 200:
        raise ControlError("Programmation absente ou incoherente")
    seen: set[int] = set()
    for event in events:
        if not isinstance(event, dict) or any(type(event.get(k)) is not int for k in ("d", "t", "mm")):
            raise ControlError("Evenement horaire invalide")
        d, t, mode = event["d"], event["t"], event["mm"]
        if not 0 <= d <= 6 or not 1440 * d <= t < 1440 * (d + 1) or mode not in {int(x) for x in _VALID_PILOT}:
            raise ControlError("Evenement hors plage ou mode inconnu")
        if t in seen:
            raise ControlError("Doublon d'evenement horaire")
        seen.add(t)
    return deepcopy(events)


def _merge_allowed(target: _PlannedThermostat, update: dict[str, Any], *, check_diff: bool = True) -> None:
    allowed = frozenset(update)
    if not allowed <= {"workingMode", "comfortTemp", "weeklyEvents", "holidays"}:
        raise ControlError("Ecriture d'un champ non autorise")
    for key, value in update.items():
        target.after[key] = deepcopy(value)
    if check_diff and any(target.before.get(key) != target.after.get(key) for key in set(target.before) | set(target.after)
                          if key not in allowed):
        raise ControlError("Champ non autorise modifie")
    if target.after.get("loadShedding") is not False:
        raise ControlError("Le plan modifie loadShedding")
    target.permitted = allowed | target.permitted


def _summarize_changes(target: str, field: str, before: Any, after: Any) -> tuple[ControlChange, ...]:
    """Safe, specific preview. Never output arbitrary raw service properties."""
    if before == after:
        return ()
    if field == "weeklyEvents":
        old = {event["t"]: event["mm"] for event in before}
        new = {event["t"]: event["mm"] for event in after}
        result = []
        for minute in sorted(set(old) | set(new)):
            if old.get(minute) != new.get(minute):
                day, minute_in_day = divmod(minute, 1440)
                label = f"weeklyEvents[d={day} {minute_in_day // 60:02d}:{minute_in_day % 60:02d}]"
                result.append(ControlChange(target, label, old.get(minute), new.get(minute)))
        return tuple(result)
    if field == "holidays":
        before_h = before if isinstance(before, dict) else {}
        after_h = after if isinstance(after, dict) else {}
        changes = []
        for key in ("mm", "until"):
            if before_h.get(key) != after_h.get(key):
                # mm and until are the ONLY disclosed holiday fields.
                changes.append(ControlChange(target, "holidays." + key,
                                             before_h.get(key), after_h.get(key)))
        return tuple(changes)
    if field in {"workingMode", "comfortTemp", "isAtHome"}:
        return (ControlChange(target, field, before, after),)
    return (ControlChange(target, "unknown", None, None),)


def _matches_after(current: dict[str, Any], plan: _PlannedThermostat) -> bool:
    for field in _INVARIANTS - plan.permitted:
        if current.get(field) != plan.before.get(field):
            raise WriteUncertainError("Champ de securite modifie apres PUT")
    for field in plan.permitted:
        if field == "holidays" and "holidays" not in plan.after:
            # Cancelled holiday: stale metadata can remain on server.
            continue
        if current.get(field) != plan.after.get(field):
            return False
    return True
