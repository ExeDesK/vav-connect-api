"""Never contacts Otodo: all control tests use an in-process synthetic gateway."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest
from aiohttp import web

from conftest import fake_gateway, new_tokens
from vav_connect import (
    ControlError, PartialWriteError, PilotMode, VAVClient, WeekEvent,
    WorkingMode, WriteUncertainError,
)


class SyntheticGateway:
    def __init__(self, count=5, *, in_holidays=False, load_shedding=False):
        self.homes = {"_id": "home-test", "isAtHome": True, "isActivated": True, "isSuspended": False}
        self.services = {}
        self.rooms = []
        self.sent = []
        self.reads = 0
        self.fail_put_id = None
        self.unknown_put_id = None
        self.pause_on_read = False
        self.external_mutation = False
        self.extra_after_first_read = False
        for number in range(1, count + 1):
            room = f"room-{number}"
            sid = str(23891 + number)
            self.rooms.append({"_id": room, "name": f"Zone {number}", "isReadOnly": False})
            self.services[sid] = {
                "_id": int(sid), "type": "thermostat", "hubId": "hub-test", "homeId": "home-test",
                "roomId": room, "isActive": True, "workingMode": 7 if in_holidays else 0,
                "comfortTemp": 19, "loadShedding": load_shedding,
                "learning": {"state": 0, "upper": "MOCK_NONTOKEN"}, "hysteresis": 1,
                "sensors": {"temp": {"deviceId": number, "endpointIndex": 0, "capabilityId": 4}},
                "modules": [{"deviceId": 100 + number, "endpointIndex": 0, "capabilityId": 6}],
                "weeklyEvents": [
                    {"d": d, "t": 1440 * d + 360, "mm": 2} for d in range(7)
                ] + [
                    {"d": d, "t": 1440 * d + 540, "mm": 3} for d in range(7)
                ],
                "holidays": {"until": "2026-11-01T17:00:00.000Z", "mm": 8},
                "updatedAt": "2026-10-18T14:00:00.000Z", "enableReports": True,
            }

    async def __call__(self, req):
        self.sent.append((req.method, req.path))
        if req.path == "/authenticate":
            return web.json_response(new_tokens())
        assert req.headers.get("token") == "access-test-1"
        if req.method == "PATCH" and req.path == "/homes/home-test":
            assert set(await req.json()) == {"isAtHome"}
            self.homes["isAtHome"] = (await req.json())["isAtHome"]
            return web.json_response(deepcopy(self.homes))
        if req.method == "PUT" and req.path.startswith("/hubs/hub-test/local-services/"):
            sid = req.path.split("/")[-1]
            if sid == self.fail_put_id:
                return web.Response(status=503, text="SHOULD_NOT_BE_LOGGED")
            if sid == self.unknown_put_id:
                return web.Response(status=204)
            body = await req.json()
            assert body["loadShedding"] is False
            assert body["learning"] == self.services[sid]["learning"]
            assert body["modules"] == self.services[sid]["modules"]
            assert body["sensors"] == self.services[sid]["sensors"]
            assert body["hysteresis"] == self.services[sid]["hysteresis"]
            updated = deepcopy(body)
            updated["updatedAt"] = "2026-10-18T14:10:00.000Z"
            # Otodo may retain last holiday settings even when omitted on PUT.
            if "holidays" not in updated:
                updated["holidays"] = deepcopy(self.services[sid]["holidays"])
            self.services[sid] = updated
            return web.json_response({"result": True})
        if req.method != "GET":
            return web.Response(status=404)
        if req.path == "/homes":
            return web.json_response(deepcopy(self.homes))
        if req.path == "/hubs":
            return web.json_response([{"_id": "hub-test", "label": "Mock hub", "wifiPwd": "PRIVATE"}])
        if req.path == "/rooms":
            return web.json_response(deepcopy(self.rooms))
        if req.path == "/devices":
            return web.json_response([])
        if req.path == "/hubs/hub-test/local-services":
            self.reads += 1
            if self.external_mutation and self.reads >= 3:
                self.services["23892"]["comfortTemp"] = 22
            visible = list(deepcopy(self.services).values())
            if self.extra_after_first_read and self.reads == 1:
                visible = [item for item in visible if item["_id"] != 99999]
            return web.json_response(visible)
        return web.Response(status=404)


def write_count(api):
    return sum(method in {"PATCH", "PUT"} for method, _ in api.sent)


@pytest.mark.asyncio
async def test_default_preview_and_two_gates():
    api = SyntheticGateway(1)
    async with fake_gateway(api) as base:
        async with VAVClient("a@b.c", "testpass", base_url=base) as client:
            preview = await client.set_working_mode("23892", WorkingMode.COMFORT_MINUS_TWO)
            assert preview.applied is False
            assert preview.mutations == 0
            assert len(preview.changes) == 1
            assert preview.changes[0].after == 3
            assert not write_count(api)
            with pytest.raises(ControlError, match="desactivees"):
                await client.set_working_mode("23892", WorkingMode.COMFORT_MINUS_TWO, apply=True)
    assert write_count(api) == 0


@pytest.mark.asyncio
async def test_live_individual_mode_updates_and_reads_back_without_losing_fields():
    api = SyntheticGateway(1)
    async with fake_gateway(api) as base:
        async with VAVClient("a@b.c", "testpass", base_url=base, allow_writes=True) as client:
            result = await client.set_working_mode("23892", WorkingMode.COMFORT_MINUS_TWO, apply=True)
            assert result.applied and result.mutations == 1
            assert api.services["23892"]["workingMode"] == 3
            assert api.services["23892"]["loadShedding"] is False
            assert api.services["23892"]["holidays"]["mm"] == 8
            assert sum(method == "PUT" for method, _ in api.sent) == 1
            another = await client.set_working_mode("23892", WorkingMode.COMFORT_MINUS_TWO, apply=True)
            assert another.mutations == 0  # idempotent


@pytest.mark.asyncio
async def test_temperature_and_preserved_holiday_metadata_on_auto():
    api = SyntheticGateway(1)
    async with fake_gateway(api) as base:
        async with VAVClient("a@b.c", "testpass", base_url=base, allow_writes=True) as client:
            result = await client.set_comfort_temperature("23892", 20.5, apply=True)
            assert result.mutations == 1
            assert api.services["23892"]["comfortTemp"] == 20.5
            assert "holidays" in api.services["23892"]


@pytest.mark.asyncio
async def test_single_schedule_day_replacement_preserves_other_days():
    api = SyntheticGateway(1)
    before = deepcopy(api.services["23892"]["weeklyEvents"])
    monday = [
        WeekEvent(0, 480, PilotMode.COMFORT),
        WeekEvent(0, 540, PilotMode.ECO),
        WeekEvent(0, 1140, PilotMode.COMFORT),
    ]
    async with fake_gateway(api) as base:
        async with VAVClient("a@b.c", "testpass", base_url=base, allow_writes=True) as client:
            preview = await client.replace_schedule_days("23892", {0: monday})
            assert len(preview.changes) >= 2
            assert any("08:00" in c.field for c in preview.changes)
            assert not write_count(api)
            result = await client.replace_schedule_days("23892", {0: monday}, apply=True)
            assert result.mutations == 1
    after = api.services["23892"]["weeklyEvents"]
    assert [e for e in after if e["d"] == 0] == [
        {"d": 0, "t": 480, "mm": 2},
        {"d": 0, "t": 540, "mm": 3},
        {"d": 0, "t": 1140, "mm": 2},
    ]
    for day in range(1, 7):
        assert [e for e in before if e["d"] == day] == [e for e in after if e["d"] == day]


@pytest.mark.asyncio
async def test_full_schedule_replaces_all_events_in_one_put():
    api = SyntheticGateway(1)
    entries = [WeekEvent(d, d * 1440 + 480, PilotMode.ECO) for d in range(7)]
    async with fake_gateway(api) as base:
        async with VAVClient("a@b.c", "testpass", base_url=base, allow_writes=True) as client:
            result = await client.set_weekly_schedule("23892", entries, apply=True)
            assert result.mutations == 1
    assert len(api.services["23892"]["weeklyEvents"]) == 7


@pytest.mark.asyncio
async def test_global_away_home_are_six_mutations_each_and_preserve_schedule():
    api = SyntheticGateway()
    prior_schedule = deepcopy(api.services["23895"]["weeklyEvents"])
    async with fake_gateway(api) as base:
        async with VAVClient("a@b.c", "testpass", base_url=base, allow_writes=True) as client:
            preview = await client.set_presence(False)
            assert len(preview.changes) == 6
            assert not write_count(api)
            applied = await client.set_presence(False, apply=True)
            assert applied.mutations == 6
            assert api.homes["isAtHome"] is False
            assert all(t["workingMode"] == 4 for t in api.services.values())
            returned = await client.set_presence(True, apply=True)
            assert returned.mutations == 6
            assert api.homes["isAtHome"] is True
            assert all(t["workingMode"] == 0 for t in api.services.values())
            assert api.services["23895"]["weeklyEvents"] == prior_schedule


@pytest.mark.asyncio
async def test_holidays_activation_is_five_puts_no_home_patch():
    api = SyntheticGateway()
    until = datetime.now(timezone.utc) + timedelta(days=5)
    async with fake_gateway(api) as base:
        async with VAVClient("a@b.c", "testpass", base_url=base, allow_writes=True) as client:
            result = await client.set_holidays(until=until, pilot_mode=PilotMode.FROST_PROTECTION, apply=True)
            assert result.mutations == 5
            assert api.homes["isAtHome"] is True
            assert all(t["workingMode"] == 7 and t["holidays"]["mm"] == 8
                       for t in api.services.values())
            assert not any(method == "PATCH" for method, _ in api.sent)


@pytest.mark.asyncio
async def test_cancel_holidays_preserves_historic_metadata_and_skips_auto():
    api = SyntheticGateway(in_holidays=True)
    api.services["23892"]["workingMode"] = 0  # previous partial cancellation
    async with fake_gateway(api) as base:
        async with VAVClient("a@b.c", "testpass", base_url=base, allow_writes=True) as client:
            res = await client.cancel_holidays(apply=True)
            assert res.mutations == 4
            assert all(t["workingMode"] == 0 and "holidays" in t for t in api.services.values())
            assert api.homes["isAtHome"] is True
            assert not any(method == "PATCH" for method, _ in api.sent)
            assert sum(method == "PUT" for method, _ in api.sent) == 4


@pytest.mark.asyncio
async def test_cancel_holidays_after_away_patches_home():
    api = SyntheticGateway(count=1, in_holidays=True)
    api.homes["isAtHome"] = False
    async with fake_gateway(api) as base:
        async with VAVClient("a@b.c", "testpass", base_url=base, allow_writes=True) as client:
            result = await client.cancel_holidays(apply=True)
            assert result.mutations == 2
            assert api.homes["isAtHome"] is True


@pytest.mark.asyncio
async def test_partial_global_failure_never_retries_and_gives_confirmed_count():
    api = SyntheticGateway(count=3)
    api.fail_put_id = "23893"
    async with fake_gateway(api) as base:
        async with VAVClient("a@b.c", "testpass", base_url=base, allow_writes=True) as client:
            with pytest.raises(PartialWriteError) as e:
                await client.set_presence(False, apply=True)
            # PATCH + salon confirmed; cuisine fails; entree not sent.
            assert len(e.value.completed) == 2
            assert e.value.uncertain_target == "23893"
    assert sum(path.endswith("23893") and method == "PUT" for method, path in api.sent) == 1
    assert api.services["23894"]["workingMode"] == 0


@pytest.mark.asyncio
async def test_write_uncertain_on_http_204_no_retries():
    api = SyntheticGateway(count=1)
    api.unknown_put_id = "23892"
    async with fake_gateway(api) as base:
        async with VAVClient("a@b.c", "testpass", base_url=base, allow_writes=True) as client:
            with pytest.raises(WriteUncertainError):
                await client.set_working_mode("23892", WorkingMode.ECO, apply=True)
    assert sum(method == "PUT" for method, _ in api.sent) == 1


@pytest.mark.asyncio
async def test_loadshedding_true_fails_closed_before_any_write():
    api = SyntheticGateway(load_shedding=True)
    async with fake_gateway(api) as base:
        async with VAVClient("a@b.c", "testpass", base_url=base, allow_writes=True) as client:
            with pytest.raises(ControlError, match="loadShedding"):
                await client.set_presence(False, apply=True)
    assert write_count(api) == 0


@pytest.mark.asyncio
async def test_external_intervention_detected_by_fresh_get_before_put():
    api = SyntheticGateway(count=1)
    api.external_mutation = True
    async with fake_gateway(api) as base:
        async with VAVClient("a@b.c", "testpass", base_url=base, allow_writes=True) as client:
            with pytest.raises(ControlError, match="modifie"):
                await client.set_working_mode("23892", WorkingMode.ECO, apply=True)
    assert not write_count(api)


@pytest.mark.parametrize("mode", [WorkingMode.HOLIDAYS, PilotMode.FROST_PROTECTION, 4, True])
@pytest.mark.asyncio
async def test_reject_wrong_mode_family(mode):
    api = SyntheticGateway(1)
    async with fake_gateway(api) as base:
        async with VAVClient("a@b.c", "testpass", base_url=base, allow_writes=True) as client:
            with pytest.raises(ValueError):
                await client.set_working_mode("23892", mode, apply=True)
    assert not write_count(api)


@pytest.mark.parametrize("temp", [float("nan"), 15, 29, 20.2, True])
@pytest.mark.asyncio
async def test_reject_unsafe_temp(temp):
    api = SyntheticGateway(1)
    async with fake_gateway(api) as base:
        async with VAVClient("a@b.c", "testpass", base_url=base) as client:
            with pytest.raises(ValueError):
                await client.set_comfort_temperature("23892", temp)
    assert not write_count(api)


@pytest.mark.parametrize("pilot", [PilotMode.COMFORT, PilotMode.COMFORT_MINUS_ONE, WorkingMode.ECO, 3])
@pytest.mark.asyncio
async def test_holidays_rejects_non_holiday_modes(pilot):
    api = SyntheticGateway(1)
    async with fake_gateway(api) as base:
        async with VAVClient("a@b.c", "testpass", base_url=base) as client:
            with pytest.raises(ValueError):
                await client.set_holidays(until=datetime.now(timezone.utc) + timedelta(days=2), pilot_mode=pilot)
    assert not write_count(api)


@pytest.mark.asyncio
async def test_unknown_field_not_printed_and_no_private_data_in_public_preview():
    api = SyntheticGateway(1)
    api.services["23892"]["installerSecret"] = "ZIGBEE-PRIVATE-KEY-DO-NOT-LEAK"
    async with fake_gateway(api) as base:
        async with VAVClient("a@b.c", "testpass", base_url=base) as client:
            preview = await client.set_working_mode("23892", WorkingMode.ECO)
            assert "ZIGBEE-PRIVATE" not in repr(preview)
            assert "ZIGBEE-PRIVATE" not in repr(client)


def test_write_config_requires_bool():
    with pytest.raises(ValueError):
        VAVClient("a@b.c", "pass", allow_writes=1)

@pytest.mark.asyncio
async def test_unknown_extra_thermostat_prevents_partial_discovery_global_command():
    api = SyntheticGateway(1)
    phantom = deepcopy(api.services["23892"])
    phantom["_id"] = 99999
    phantom["roomId"] = "room-orphan"
    api.services["99999"] = phantom
    api.extra_after_first_read = True
    async with fake_gateway(api) as base:
        async with VAVClient("a@b.c", "testpass", base_url=base, allow_writes=True) as client:
            with pytest.raises(ControlError, match="incompl"):
                await client.set_presence(False, apply=True)
    assert write_count(api) == 0


@pytest.mark.asyncio
async def test_mode_change_while_holidays_active_is_refused():
    api = SyntheticGateway(1, in_holidays=True)
    async with fake_gateway(api) as base:
        async with VAVClient("a@b.c", "testpass", base_url=base, allow_writes=True) as client:
            with pytest.raises(ControlError, match="incompatible"):
                await client.set_working_mode("23892", WorkingMode.ECO, apply=True)
            with pytest.raises(ControlError, match="Vacances"):
                await client.set_presence(True, apply=True)
    assert write_count(api) == 0


@pytest.mark.asyncio
async def test_reject_duplicate_weekly_events_without_writing():
    api = SyntheticGateway(1)
    events = [WeekEvent(0, 480, PilotMode.COMFORT), WeekEvent(0, 480, PilotMode.ECO)]
    async with fake_gateway(api) as base:
        async with VAVClient("a@b.c", "testpass", base_url=base, allow_writes=True) as client:
            with pytest.raises(ControlError, match="Doublon"):
                await client.set_weekly_schedule("23892", events, apply=True)
    assert write_count(api) == 0


@pytest.mark.asyncio
async def test_holidays_inactive_metadata_retained_when_changing_confort():
    api = SyntheticGateway(1)
    api.services["23892"]["workingMode"] = 0
    async with fake_gateway(api) as base:
        async with VAVClient("a@b.c", "testpass", base_url=base, allow_writes=True) as client:
            assert (await client.set_comfort_temperature("23892", 20, apply=True)).mutations == 1
    assert api.services["23892"]["holidays"]["mm"] == 8
    assert api.services["23892"]["workingMode"] == 0
