import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from aiohttp import web

from conftest import fake_gateway, new_tokens
from vav_connect import AuthenticationError, ProtocolError, RateLimitError, SessionTokens, VAVClient, WorkingMode


@pytest.mark.asyncio
async def test_snapshot_gets_real_paths_and_redacts_secrets() -> None:
    called: list[tuple[str, str]] = []

    async def handler(req):
        called.append((req.method, req.path))
        if req.path == "/authenticate":
            assert req.method == "POST"
            assert await req.json() == {
                "email": "user@example.test", "password": "not-a-real-password", "parkName": "vav",
            }
            assert "token" not in req.headers
            return web.json_response(new_tokens())
        assert req.method == "GET"
        assert req.headers["token"] == "access-test-1"
        assert req.headers["language"] == "fr"
        assert req.headers["mobileversion"] == "4.14.4"
        assert req.headers["timezoneid"] == "GMT"
        if req.path == "/homes":
            return web.json_response({
                "_id": "home-test", "isAtHome": True, "isActivated": True,
                "energy": {"usagePointId": "PRIVATE_METER_ID"},
                "email": "PRIVATE_EMAIL",
            })
        if req.path == "/hubs":
            return web.json_response([{"_id": "hub-test", "label": "Ma box", "state": 1,
                                       "aesKey": "PRIVATE_ZIGBEE_KEY", "secretKey": "PRIVATE_HUB_KEY",
                                       "wifiPwd": "PRIVATE_WIFI_PASSWORD"}])
        if req.path == "/rooms":
            return web.json_response([{"_id": "room-test", "name": "Salon", "isReadOnly": False}])
        if req.path == "/devices":
            return web.json_response([
                {"_id": 11, "name": "Capteur salon", "roomId": "room-test",
                 "properties": {"keyList": [{"v": "PRIVATE_ZIGBEE_KEY"}]},
                 "endpoints": [{"index": 0, "capabilities": [
                     {"_id": 4, "value": 2973, "unit": "Kelvin"},
                     {"_id": 15, "value": 54, "unit": "%"}]}]},
                {"_id": 12, "name": "Module salon", "endpoints": [{"index": 0,
                 "capabilities": [{"_id": 6, "value": 0}]}]},
            ])
        if req.path == "/hubs/hub-test/local-services":
            return web.json_response([{
                "_id": 42, "type": "thermostat", "roomId": "room-test", "hubId": "hub-test",
                "workingMode": 0, "comfortTemp": 20, "weeklyEvents": [],
                "sensors": {"temp": {"deviceId": 11, "endpointIndex": 0, "capabilityId": 4}},
                "modules": [{"deviceId": 12, "endpointIndex": 0, "capabilityId": 6}],
                "loadShedding": False,
            }])
        return web.Response(status=404)

    async with fake_gateway(handler) as base_url:
        async with VAVClient("user@example.test", "not-a-real-password", base_url=base_url) as client:
            result = await client.get_snapshot()
            assert result.home.is_at_home is True
            assert result.zones[0].name == "Salon"
            assert result.zones[0].temperature_c == 24.15
            assert result.zones[0].pilot_mode.value == 0
            assert result.zones[0].thermostat.working_mode == WorkingMode.AUTO
            text = repr(result)
            for secret in ("PRIVATE_METER_ID", "PRIVATE_EMAIL", "PRIVATE_HUB_KEY", "PRIVATE_ZIGBEE_KEY", "PRIVATE_WIFI_PASSWORD"):
                assert secret not in text
            assert client.tokens is not None
        assert called == [
            ("POST", "/authenticate"), ("GET", "/homes"), ("GET", "/hubs"),
            ("GET", "/rooms"), ("GET", "/devices"),
            ("GET", "/hubs/hub-test/local-services"),
        ]


@pytest.mark.asyncio
async def test_refresh_has_no_body_and_uses_refresh_token_by_default() -> None:
    seen = []

    async def handler(req):
        seen.append((req.method, req.path, req.headers.get("token"), await req.read()))
        if req.path == "/refreshToken":
            assert req.headers.get("Content-Length") == "0"
            return web.json_response(new_tokens("access-new", "refresh-new"))
        if req.path == "/hubs":
            return web.json_response([])
        return web.Response(status=404)

    initial = SessionTokens("access-old", "refresh-old", datetime.now(timezone.utc) + timedelta(days=10))
    async with fake_gateway(handler) as base_url:
        async with VAVClient(tokens=initial, base_url=base_url) as client:
            updated = await client.refresh()
            assert updated.access_token == "access-new"
            assert updated.refresh_token == "refresh-new"
            assert await client.get_hubs() == ()
    assert seen == [
        ("POST", "/refreshToken", "refresh-old", b""),
        ("GET", "/hubs", "access-new", b""),
    ]


@pytest.mark.asyncio
async def test_access_token_header_is_selectable_for_unverified_refresh_semantics() -> None:
    seen = []

    async def handler(req):
        seen.append(req.headers.get("token"))
        return web.json_response(new_tokens("access-new", "refresh-new"))

    tokens = SessionTokens("access-old", "refresh-old", datetime.now(timezone.utc) + timedelta(days=10))
    async with fake_gateway(handler) as base:
        async with VAVClient(tokens=tokens, refresh_header_token="access", base_url=base) as client:
            await client.refresh()
    assert seen == ["access-old"]


@pytest.mark.asyncio
async def test_reactive_401_refreshes_once_then_retries_get() -> None:
    seen = []

    async def handler(req):
        seen.append((req.path, req.headers.get("token")))
        if req.path == "/rooms" and req.headers.get("token") == "access-old":
            return web.Response(status=401, text="DO_NOT_PRINT_PRIVATE_SERVER_BODY")
        if req.path == "/refreshToken":
            return web.json_response(new_tokens("access-new", "refresh-new"))
        if req.path == "/rooms":
            return web.json_response([])
        return web.Response(status=404)

    tokens = SessionTokens("access-old", "refresh-old", datetime.now(timezone.utc) + timedelta(days=10))
    async with fake_gateway(handler) as base:
        async with VAVClient(tokens=tokens, base_url=base) as client:
            assert await client.get_rooms() == ()
    assert seen == [
        ("/rooms", "access-old"),
        ("/refreshToken", "refresh-old"),
        ("/rooms", "access-new"),
    ]


@pytest.mark.asyncio
async def test_expired_token_refresh_preemptively() -> None:
    seen = []

    async def handler(req):
        seen.append(req.path)
        if req.path == "/refreshToken":
            return web.json_response(new_tokens("new-a", "new-r"))
        if req.path == "/devices":
            assert req.headers["token"] == "new-a"
            return web.json_response([])
        return web.Response(status=404)

    initial = SessionTokens("old-a", "old-r", datetime.now(timezone.utc) - timedelta(seconds=5))
    async with fake_gateway(handler) as base:
        async with VAVClient(tokens=initial, base_url=base) as client:
            assert await client.get_devices() == ()
    assert seen == ["/refreshToken", "/devices"]


@pytest.mark.asyncio
async def test_concurrent_gets_share_one_authentication() -> None:
    counts = {"auth": 0}

    async def handler(req):
        if req.path == "/authenticate":
            counts["auth"] += 1
            await asyncio.sleep(0.02)
            return web.json_response(new_tokens())
        if req.path in ("/hubs", "/rooms"):
            return web.json_response([])
        return web.Response(status=404)

    async with fake_gateway(handler) as base:
        async with VAVClient("someone@test.invalid", "a-test-secret", base_url=base) as client:
            hubs, rooms = await asyncio.gather(client.get_hubs(), client.get_rooms())
            assert hubs == rooms == ()
    assert counts["auth"] == 1


@pytest.mark.asyncio
async def test_429_does_not_retry_endlessly() -> None:
    count = 0

    async def handler(req):
        nonlocal count
        if req.path == "/authenticate":
            return web.json_response(new_tokens())
        count += 1
        return web.Response(status=429, headers={"Retry-After": "120"})

    async with fake_gateway(handler) as base:
        async with VAVClient("some@test.invalid", "only-a-test", base_url=base) as client:
            with pytest.raises(RateLimitError) as caught:
                await client.get_hubs()
            assert caught.value.retry_after == "120"
    assert count == 1


@pytest.mark.asyncio
async def test_unauthorized_refresh_without_password_fails_cleanly() -> None:
    async def handler(req):
        return web.Response(status=401, text="PRIVATE_RESPONSE_SHOULD_NOT_LEAK")

    initial = SessionTokens("old-access", "old-refresh", datetime.now(timezone.utc) - timedelta(minutes=1))
    async with fake_gateway(handler) as base:
        async with VAVClient(tokens=initial, base_url=base) as client:
            with pytest.raises(AuthenticationError) as caught:
                await client.get_hubs()
            assert "PRIVATE_RESPONSE_SHOULD_NOT_LEAK" not in str(caught.value)


@pytest.mark.asyncio
async def test_non_json_response_fails_without_raw_body() -> None:
    async def handler(req):
        if req.path == "/authenticate":
            return web.json_response(new_tokens())
        return web.Response(text="TOP_SECRET_HTML", content_type="text/html")

    async with fake_gateway(handler) as base:
        async with VAVClient("some@test.invalid", "only-a-test", base_url=base) as client:
            with pytest.raises(ProtocolError) as caught:
                await client.get_hubs()
            assert "TOP_SECRET_HTML" not in str(caught.value)


def test_no_heating_write_method_in_read_only_sdk() -> None:
    assert not hasattr(VAVClient, "set_comfort_temperature")
    assert not hasattr(VAVClient, "set_working_mode")
    with pytest.raises(ValueError):
        VAVClient("user@test.invalid", "secret", base_url="http://api.gateway.otodo.io")
