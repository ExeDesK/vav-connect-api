"""Erreurs et reprises bornees ; faux backend HTTP seulement."""

from datetime import datetime, timedelta, timezone

import pytest
from aiohttp import web

from conftest import fake_gateway, new_tokens
from vav_connect import (
    APIError, AuthenticationError, ForbiddenError, ProtocolError,
    RateLimitError, SessionTokens, VAVClient,
)


def _tokens() -> SessionTokens:
    return SessionTokens("ACCESS_SAFE", "REFRESH_SAFE", datetime.now(timezone.utc) + timedelta(days=3))


@pytest.mark.asyncio
async def test_get_503_is_retried_once_and_recovers() -> None:
    count = 0

    async def handler(req):
        nonlocal count
        count += 1
        if count == 1:
            return web.Response(status=503, text="SECRET_HTML_BODY")
        assert req.headers["token"] == "ACCESS_SAFE"
        return web.json_response([])

    async with fake_gateway(handler) as base:
        async with VAVClient(tokens=_tokens(), base_url=base, retry_backoff_seconds=0) as client:
            assert await client.get_hubs() == ()
    assert count == 2


@pytest.mark.asyncio
async def test_get_503_exhausts_retries_without_body_leak() -> None:
    count = 0

    async def handler(req):
        nonlocal count
        count += 1
        return web.Response(status=503, text="TOP_SECRET_503_PAYLOAD")

    async with fake_gateway(handler) as base:
        async with VAVClient(tokens=_tokens(), base_url=base, retry_backoff_seconds=0) as client:
            with pytest.raises(APIError) as caught:
                await client.get_hubs()
    assert count == 2
    assert caught.value.status == 503
    assert "TOP_SECRET" not in str(caught.value)


@pytest.mark.asyncio
async def test_get_400_not_retried() -> None:
    count = 0

    async def handler(req):
        nonlocal count
        count += 1
        return web.Response(status=400)

    async with fake_gateway(handler) as base:
        async with VAVClient(tokens=_tokens(), base_url=base) as client:
            with pytest.raises(APIError) as caught:
                await client.get_rooms()
    assert caught.value.status == 400
    assert count == 1


@pytest.mark.asyncio
async def test_get_403_never_refreshes_or_reauthenticates() -> None:
    calls = []

    async def handler(req):
        calls.append(req.path)
        if req.path == "/hubs":
            return web.Response(status=403, text="PRIVATE_PERMISSION_DATA")
        return web.Response(status=500)

    async with fake_gateway(handler) as base:
        async with VAVClient(tokens=_tokens(), base_url=base) as client:
            with pytest.raises(ForbiddenError) as error:
                await client.get_hubs()
    assert calls == ["/hubs"]
    assert error.value.status == 403
    assert "PRIVATE_PERMISSION_DATA" not in str(error.value)


@pytest.mark.asyncio
async def test_refresh_503_is_never_retried() -> None:
    calls = []

    async def handler(req):
        calls.append(req.path)
        return web.Response(status=503)

    async with fake_gateway(handler) as base:
        async with VAVClient(tokens=_tokens(), base_url=base) as client:
            with pytest.raises(APIError):
                await client.refresh()
    assert calls == ["/refreshToken"]


@pytest.mark.asyncio
async def test_rate_limit_with_retry_after_never_retries() -> None:
    calls = []

    async def handler(req):
        calls.append(req.path)
        return web.Response(status=429, headers={"Retry-After": "45"})

    async with fake_gateway(handler) as base:
        async with VAVClient(tokens=_tokens(), base_url=base) as client:
            with pytest.raises(RateLimitError) as error:
                await client.get_devices()
    assert calls == ["/devices"]
    assert error.value.retry_after_seconds == 45


def test_rate_limit_invalid_retry_after_is_safe() -> None:
    assert RateLimitError("GET", "/homes", "not a number or date").retry_after_seconds is None
    assert RateLimitError("GET", "/homes", "-2").retry_after_seconds is None
    assert RateLimitError("GET", "/homes", "0").retry_after_seconds == 0


@pytest.mark.asyncio
async def test_302_redirect_is_never_followed_with_custom_token() -> None:
    calls = []

    async def handler(req):
        calls.append(req.path)
        if req.path == "/rooms":
            return web.Response(status=302, headers={"Location": "/attacker"})
        if req.path == "/attacker":
            raise AssertionError("Le token ne doit jamais atteindre /attacker")
        return web.Response(status=404)

    async with fake_gateway(handler) as base:
        async with VAVClient(tokens=_tokens(), base_url=base) as client:
            with pytest.raises(ProtocolError):
                await client.get_rooms()
    assert calls == ["/rooms"]


@pytest.mark.asyncio
async def test_304_cache_miss_raises_protocol_error_without_retry() -> None:
    count = 0

    async def handler(req):
        nonlocal count
        count += 1
        return web.Response(status=304)

    async with fake_gateway(handler) as base:
        async with VAVClient(tokens=_tokens(), base_url=base) as client:
            with pytest.raises(ProtocolError):
                await client.get_hubs()
    assert count == 1


@pytest.mark.asyncio
async def test_reactive_401_twice_has_only_one_refresh() -> None:
    seen = []

    async def handler(req):
        seen.append(req.path)
        if req.path == "/hubs":
            return web.Response(status=401)
        if req.path == "/refreshToken":
            return web.json_response(new_tokens("ACCESS_NEW", "REFRESH_NEW"))
        return web.Response(status=404)

    async with fake_gateway(handler) as base:
        async with VAVClient(tokens=_tokens(), base_url=base) as client:
            with pytest.raises(AuthenticationError):
                await client.get_hubs()
    assert seen == ["/hubs", "/refreshToken", "/hubs"]


@pytest.mark.asyncio
async def test_api_health_is_cloud_status_not_hub_reachability() -> None:
    async def handler(req):
        assert req.path == "/health"
        return web.json_response({"health": "ok"})

    async with fake_gateway(handler) as base:
        async with VAVClient(tokens=_tokens(), base_url=base) as client:
            assert await client.get_api_health() == "ok"


def test_client_config_rejects_unsafe_inputs() -> None:
    with pytest.raises(ValueError):
        VAVClient(tokens=_tokens(), max_read_retries=4)
    with pytest.raises(ValueError):
        VAVClient(tokens=_tokens(), max_read_retries=True)
    with pytest.raises(ValueError):
        VAVClient(tokens=_tokens(), retry_backoff_seconds=-1)
    with pytest.raises(ValueError):
        VAVClient(tokens=_tokens(), retry_backoff_seconds=float("nan"))
    with pytest.raises(ValueError):
        VAVClient(tokens=_tokens(), timeout_seconds=True)
    with pytest.raises(ValueError):
        VAVClient(tokens=_tokens(), base_url="http://vav.example.invalid")


@pytest.mark.asyncio
async def test_connection_refused_raises_transport_error(unused_tcp_port) -> None:
    """Une erreur TCP ne doit jamais exposer le header de session."""
    from vav_connect import TransportError

    async with VAVClient(tokens=_tokens(), base_url=f"http://127.0.0.1:{unused_tcp_port}",
                         timeout_seconds=0.1, retry_backoff_seconds=0) as client:
        with pytest.raises(TransportError) as caught:
            await client.get_hubs()
    assert "ACCESS_SAFE" not in str(caught.value)
    assert "REFRESH_SAFE" not in str(caught.value)


@pytest.mark.asyncio
async def test_get_timeout_raises_transport_error_without_unbounded_wait() -> None:
    import asyncio
    from vav_connect import TransportError

    async def slow_handler(_req):
        await asyncio.sleep(0.1)
        return web.json_response([])

    async with fake_gateway(slow_handler) as base:
        async with VAVClient(tokens=_tokens(), base_url=base, timeout_seconds=0.02,
                             max_read_retries=0) as client:
            with pytest.raises(TransportError):
                await client.get_hubs()
