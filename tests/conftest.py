"""Faux serveur Otodo local. Aucune connexion au vrai cloud dans les tests."""

from contextlib import asynccontextmanager

from aiohttp import web


@asynccontextmanager
async def fake_gateway(handler):
    app = web.Application()
    app.router.add_route("*", "/{tail:.*}", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="127.0.0.1", port=0)
    await site.start()
    try:
        port = site._server.sockets[0].getsockname()[1]
        yield f"http://127.0.0.1:{port}"
    finally:
        await runner.cleanup()


def new_tokens(access="access-test-1", refresh="refresh-test-1"):
    return {
        "token_type": "Bearer",
        "access_token": access,
        "refresh_token": refresh,
        "expires_in": 2592000,
        "homeId": "home-test",
        "parkId": "park-test",
        "userId": "user-test",
    }
