"""Rotation reelle simulee, sans aucun secret ou acces cloud reel."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from aiohttp import web

from conftest import fake_gateway, new_tokens
from vav_connect import (
    AuthenticationError, ProtocolError, SessionTokens, TokenPersistenceError,
    VAVClient,
)


def _stored_session() -> SessionTokens:
    return SessionTokens(
        "SYNTHETIC_ACCESS", "SYNTHETIC_REFRESH",
        datetime.now(timezone.utc) + timedelta(days=15),
        home_id="home-local", park_id="park-local", user_id="user-local",
    )


def test_roundtrip_persistence_timezone_aware_and_no_secret_repr() -> None:
    before = _stored_session()
    stored = before.to_storage()
    assert stored["schema_version"] == 1
    assert stored["access_token"] == "SYNTHETIC_ACCESS"
    restored = SessionTokens.from_storage(stored)
    assert restored == before
    assert restored.expires_at.tzinfo is not None
    assert "SYNTHETIC_ACCESS" not in repr(restored)
    assert "SYNTHETIC_REFRESH" not in repr(restored)
    assert "SYNTHETIC_ACCESS" not in repr(VAVClient(tokens=restored))


@pytest.mark.parametrize("invalid", [
    {},
    {"schema_version": 2},
    {"schema_version": True},
    {"schema_version": 1, "expires_at": "SECRET_UNPARSEABLE_DATE"},
    {"schema_version": 1, "expires_at": "2026-10-18T14:00:00"},
])
def test_invalid_stored_session_fails_without_leaking_values(invalid) -> None:
    with pytest.raises(ProtocolError) as error:
        SessionTokens.from_storage(invalid)
    assert "SECRET_UNPARSEABLE_DATE" not in str(error.value)


def test_reject_invalid_expiry_from_api() -> None:
    for invalid in (0, -1, "30", True, 9999999999999):
        response = new_tokens()
        response["expires_in"] = invalid
        with pytest.raises(ProtocolError):
            SessionTokens.from_response(response)


@pytest.mark.asyncio
async def test_refresh_rotates_and_persists_both_tokens_for_restart() -> None:
    persisted = []
    seen_refresh_tokens = []

    async def save(tokens: SessionTokens) -> None:
        persisted.append(tokens.to_storage())

    async def handler(req):
        if req.path == "/refreshToken":
            assert await req.read() == b""
            seen_refresh_tokens.append(req.headers["token"])
            return web.json_response(new_tokens(f"access-{len(seen_refresh_tokens)}", f"refresh-{len(seen_refresh_tokens)}"))
        if req.path == "/homes":
            return web.json_response({"_id": "home-local", "isAtHome": True})
        return web.Response(status=404)

    initial = _stored_session()
    async with fake_gateway(handler) as base:
        async with VAVClient(tokens=initial, base_url=base, token_callback=save) as client:
            await client.refresh()
            assert persisted[0]["access_token"] == "access-1"
            assert persisted[0]["refresh_token"] == "refresh-1"
            assert client.tokens is not None
            assert client.tokens.home_id == "home-test"  # Donnees plus recentes retournees par Otodo

        # Reprise simulee au redemarrage : nouveau SDK, jetons sauves.
        restored = SessionTokens.from_storage(persisted[0])
        async with VAVClient(tokens=restored, base_url=base, token_callback=save) as client:
            await client.refresh()
            assert (await client.get_home()).is_at_home is True
    assert seen_refresh_tokens == ["SYNTHETIC_REFRESH", "refresh-1"]
    assert persisted[1]["refresh_token"] == "refresh-2"


@pytest.mark.asyncio
async def test_refresh_keeps_metadata_if_response_omits_it() -> None:
    initial = _stored_session()

    async def handler(req):
        # Certains backends omettent les metadonnees au renouvellement.
        return web.json_response({
            "access_token": "NEW_ACCESS", "refresh_token": "NEW_REFRESH", "expires_in": 2592000,
        })

    async with fake_gateway(handler) as base:
        async with VAVClient(tokens=initial, base_url=base) as client:
            refreshed = await client.refresh()
    assert refreshed.home_id == initial.home_id
    assert refreshed.park_id == initial.park_id
    assert refreshed.user_id == initial.user_id


@pytest.mark.asyncio
async def test_callback_failure_does_not_rollback_rotated_tokens_or_expose_secrets() -> None:
    async def broken_callback(tokens: SessionTokens) -> None:
        raise RuntimeError(f"DO_NOT_LEAK_THE_TOKEN_{tokens.refresh_token}")

    async def handler(req):
        return web.json_response(new_tokens("ACCESS_CHANGED", "REFRESH_CHANGED"))

    async with fake_gateway(handler) as base:
        async with VAVClient(tokens=_stored_session(), base_url=base,
                             token_callback=broken_callback) as client:
            with pytest.raises(TokenPersistenceError) as caught:
                await client.refresh()
            assert client.tokens is not None
            assert client.tokens.access_token == "ACCESS_CHANGED"
            assert client.tokens.refresh_token == "REFRESH_CHANGED"
            assert "REFRESH_CHANGED" not in str(caught.value)
            assert "DO_NOT_LEAK" not in str(caught.value)
            assert caught.value.__cause__ is None


@pytest.mark.asyncio
async def test_expired_parallel_reads_trigger_one_refresh_and_one_callback() -> None:
    counts = {"refresh": 0, "callbacks": 0}

    async def on_tokens(_tokens: SessionTokens) -> None:
        counts["callbacks"] += 1
        await asyncio.sleep(0.01)

    async def handler(req):
        if req.path == "/refreshToken":
            counts["refresh"] += 1
            return web.json_response(new_tokens("ACCESS_NEW", "REFRESH_NEW"))
        if req.path in ("/hubs", "/rooms"):
            assert req.headers["token"] == "ACCESS_NEW"
            return web.json_response([])
        return web.Response(status=404)

    expired = SessionTokens("ACCESS_OLD", "REFRESH_OLD", datetime.now(timezone.utc) - timedelta(days=1))
    async with fake_gateway(handler) as base:
        async with VAVClient(tokens=expired, base_url=base, token_callback=on_tokens) as client:
            hubs, rooms = await asyncio.gather(client.get_hubs(), client.get_rooms())
            assert hubs == rooms == ()
    assert counts == {"refresh": 1, "callbacks": 1}
