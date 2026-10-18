"""Essais du diagnostic contre un faux serveur local, jamais Otodo reel."""

import importlib
from pathlib import Path
import sys

import pytest
from aiohttp import web

from conftest import fake_gateway, new_tokens


@pytest.fixture
def probe_module(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "examples"))
    return importlib.import_module("verify_refresh")


@pytest.mark.asyncio
async def test_live_probe_success_with_refresh_header(probe_module, capsys):
    requests = []

    async def handler(req):
        requests.append((req.method, req.path, req.headers.get("token"), await req.read()))
        if req.path == "/authenticate":
            return web.json_response(new_tokens("access-before", "refresh-before"))
        if req.path == "/refreshToken":
            assert req.headers["token"] == "refresh-before"
            assert req.headers.get("Content-Length") == "0"
            return web.json_response(new_tokens("access-after", "refresh-after"))
        if req.path == "/homes":
            assert req.headers["token"] in {"access-before", "access-after"}
            return web.json_response({"_id": "SECRET_HOME_ID", "isAtHome": True})
        return web.Response(status=404)

    async with fake_gateway(handler) as base_url:
        exit_code = await probe_module.probe_refresh(
            "hidden@test.invalid", "PASSWORD_DO_NOT_PRINT", base_url=base_url
        )
    assert exit_code == 0
    assert requests == [
        ("POST", "/authenticate", None, b'{"email": "hidden@test.invalid", "password": "PASSWORD_DO_NOT_PRINT", "parkName": "vav"}'),
        ("GET", "/homes", "access-before", b""),
        ("POST", "/refreshToken", "refresh-before", b""),
        ("GET", "/homes", "access-after", b""),
    ]
    output = capsys.readouterr().out
    assert "RESULTAT : refresh valide" in output
    for forbidden in ("SECRET_HOME_ID", "PASSWORD_DO_NOT_PRINT", "access-before", "refresh-before", "access-after", "refresh-after"):
        assert forbidden not in output


@pytest.mark.asyncio
async def test_failed_refresh_does_not_silently_reauthenticate(probe_module, capsys):
    count = {"login": 0, "refresh": 0}

    async def handler(req):
        if req.path == "/authenticate":
            count["login"] += 1
            return web.json_response(new_tokens("access-before", "refresh-before"))
        if req.path == "/refreshToken":
            count["refresh"] += 1
            return web.Response(status=401, text="CONFIDENTIAL_BODY")
        if req.path == "/homes":
            return web.json_response({"isAtHome": True})
        return web.Response(status=404)

    async with fake_gateway(handler) as base_url:
        exit_code = await probe_module.probe_refresh(
            "hidden@test.invalid", "no-print", base_url=base_url
        )
    assert exit_code == 2
    assert count == {"login": 1, "refresh": 1}
    output = capsys.readouterr().out
    assert "ECHEC" in output and "401/403" in output
    assert "CONFIDENTIAL_BODY" not in output


@pytest.mark.asyncio
async def test_live_probe_supports_access_token_option(probe_module, capsys):
    seen = []

    async def handler(req):
        if req.path == "/authenticate":
            return web.json_response(new_tokens("access-before", "refresh-before"))
        if req.path == "/homes":
            return web.json_response({"isAtHome": True})
        if req.path == "/refreshToken":
            seen.append(req.headers["token"])
            return web.json_response(new_tokens("access-after", "refresh-after"))
        return web.Response(status=404)

    async with fake_gateway(handler) as base_url:
        exit_code = await probe_module.probe_refresh(
            "hidden@test.invalid", "no-print", base_url=base_url, header_token="access"
        )
    assert exit_code == 0
    assert seen == ["access-before"]
    assert "Jeton teste dans l'en-tete token : access" in capsys.readouterr().out


def test_cli_requires_environment(probe_module, monkeypatch, capsys):
    monkeypatch.delenv("VAV_EMAIL", raising=False)
    monkeypatch.delenv("VAV_PASSWORD", raising=False)
    monkeypatch.setattr(sys, "argv", ["verify_refresh.py"])
    assert probe_module.main() == 1
    assert "Definir VAV_EMAIL" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_refresh_success_does_not_mask_invalid_new_access(probe_module, capsys):
    seen = []

    async def handler(req):
        seen.append(req.path)
        if req.path == "/authenticate":
            return web.json_response(new_tokens("access-before", "refresh-before"))
        if req.path == "/refreshToken":
            return web.json_response(new_tokens("access-after", "refresh-after"))
        if req.path == "/homes":
            if req.headers.get("token") == "access-after":
                return web.Response(status=401, text="SECRET_ERROR_BODY")
            return web.json_response({"isAtHome": True})
        return web.Response(status=404)

    async with fake_gateway(handler) as base_url:
        code = await probe_module.probe_refresh(
            "hidden@test.invalid", "no-print", base_url=base_url,
        )
    # Le diagnostic n'autorise aucun retry automatique apres le refresh.
    assert seen.count("/refreshToken") == 1
    assert code == 2
    out = capsys.readouterr().out
    assert "[3/4] POST /refreshToken : OK" in out
    assert "RESULTAT : refresh valide" not in out
    assert "SECRET_ERROR_BODY" not in out


@pytest.mark.asyncio
async def test_429_stops_after_one_refresh(probe_module, capsys):
    attempts = 0

    async def handler(req):
        nonlocal attempts
        if req.path == "/authenticate":
            return web.json_response(new_tokens("access-before", "refresh-before"))
        if req.path == "/refreshToken":
            attempts += 1
            return web.Response(status=429)
        if req.path == "/homes":
            return web.json_response({"isAtHome": True})
        return web.Response(status=404)

    async with fake_gateway(handler) as base_url:
        code = await probe_module.probe_refresh(
            "hidden@test.invalid", "no-print", base_url=base_url,
        )
    assert code == 3
    assert attempts == 1
    assert "HTTP 429" in capsys.readouterr().out
