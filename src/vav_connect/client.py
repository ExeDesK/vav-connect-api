"""Client HTTP asynchrone (lecture seule) pour VAV Connect / Otodo.

Aucun endpoint de pilotage n'est implemente dans cette premiere version.
Les seuls POST sont /authenticate et /refreshToken.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any, Literal
from urllib.parse import quote, urlsplit

import aiohttp

from .auth import SessionTokens
from .exceptions import APIError, AuthenticationError, ProtocolError, RateLimitError, TransportError
from .models import Device, Home, Hub, Room, Snapshot, Thermostat

DEFAULT_BASE_URL = "https://api.gateway.otodo.io"
TokenCallback = Callable[[SessionTokens], Awaitable[None]]
_MISSING = object()


class VAVClient:
    """SDK VAV en lecture seule.

    `refresh_header_token='refresh'` est une HYPOTHESE non encore validee en
    capture non masquee. Utiliser `access` si le test de l'application le montre.
    Le client ne journalise jamais les tokens ni les reponses HTTP brutes.
    """

    def __init__(
        self,
        email: str | None = None,
        password: str | None = None,
        *,
        tokens: SessionTokens | None = None,
        base_url: str = DEFAULT_BASE_URL,
        park_name: str = "vav",
        session: aiohttp.ClientSession | None = None,
        timeout_seconds: float = 20,
        refresh_header_token: Literal["refresh", "access"] = "refresh",
        token_callback: TokenCallback | None = None,
    ) -> None:
        if bool(email) != bool(password):
            raise ValueError("Fournir email et mot de passe ensemble, ou des tokens existants")
        if tokens is None and not (email and password):
            raise ValueError("Fournir des identifiants ou une session deja sauvegardee")
        if refresh_header_token not in {"refresh", "access"}:
            raise ValueError("refresh_header_token doit valoir 'refresh' ou 'access'")
        parsed = urlsplit(base_url)
        if (
            (parsed.scheme != "https" and not (parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost", "::1"}))
            or not parsed.netloc
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
            or parsed.username is not None
            or parsed.password is not None
        ):
            raise ValueError("base_url doit etre HTTPS (HTTP permis uniquement en local pour les tests)")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds doit etre positif")

        self._email = email
        self._password = password
        self._park_name = park_name
        self._tokens = tokens
        self._base_url = base_url.rstrip("/")
        self._session = session
        self._owns_session = session is None
        self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self._refresh_header_token = refresh_header_token
        self._token_callback = token_callback
        self._auth_lock = asyncio.Lock()

    def __repr__(self) -> str:
        return f"VAVClient(authenticated={self._tokens is not None})"

    @property
    def tokens(self) -> SessionTokens | None:
        """Session courante, a conserver dans un stockage securise si necessaire."""
        return self._tokens

    async def __aenter__(self) -> VAVClient:
        await self._get_session()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    async def close(self) -> None:
        if self._owns_session and self._session and not self._session.closed:
            await self._session.close()
            self._session = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None:
            self._session = aiohttp.ClientSession(timeout=self._timeout)
        if self._session.closed:
            raise TransportError("La session HTTP est fermee")
        return self._session

    def _headers(self, token: str | None = None) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "language": "fr",
            "mobileversion": "4.14.4",
            "timezoneid": "GMT",
            "useragent": "android.vav.4.14.4",
            "User-Agent": "vav-connect-api/0.1.0",
        }
        if token is not None:
            headers["token"] = token
        return headers

    async def _http(
        self,
        method: Literal["GET", "POST"],
        path: str,
        *,
        token: str | None = None,
        body: object = _MISSING,
        empty_body: bool = False,
    ) -> object:
        # Verrou de securite: pas de PUT/PATCH/DELETE ni de POST de pilotage.
        if method not in {"GET", "POST"} or (method == "POST" and path not in {"/authenticate", "/refreshToken"}):
            raise ValueError("La version 0.1.0 autorise uniquement les lectures et les POST d'authentification")
        if not path.startswith("/") or path.startswith("//") or "?" in path or "#" in path:
            raise ValueError("Chemin API non valide")
        kwargs: dict[str, Any] = {"headers": self._headers(token), "timeout": self._timeout}
        if body is not _MISSING:
            kwargs["json"] = body
        elif empty_body:
            kwargs["data"] = b""
        session = await self._get_session()
        try:
            async with session.request(method, self._base_url + path, **kwargs) as response:
                if response.status in {401, 403}:
                    raise AuthenticationError(f"Authentification refusee (HTTP {response.status}, {path})")
                if response.status == 429:
                    raise RateLimitError(method, path, response.headers.get("Retry-After"))
                if response.status >= 400:
                    raise APIError(method, path, response.status)
                if response.status == 304:
                    raise ProtocolError(f"HTTP 304 sans cache exploitable sur {path}")
                if response.status == 204:
                    raise ProtocolError(f"Reponse JSON attendue, HTTP 204 sur {path}")
                try:
                    data = await response.json(content_type=None)
                except (aiohttp.ContentTypeError, json.JSONDecodeError, UnicodeDecodeError) as exc:
                    raise ProtocolError(f"Reponse non JSON sur {method} {path}") from None
                return data
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            # Ne pas integrer str(exc), qui pourrait comporter l'URL complete.
            raise TransportError(f"Echec reseau vers VAV sur {method} {path}") from None

    async def _save_tokens(self, data: object) -> SessionTokens:
        if not isinstance(data, dict):
            raise ProtocolError("La reponse de session n'est pas un objet JSON")
        tokens = SessionTokens.from_response(data)
        self._tokens = tokens
        if self._token_callback is not None:
            await self._token_callback(tokens)
        return tokens

    async def _authenticate_locked(self) -> SessionTokens:
        if not self._email or not self._password:
            raise AuthenticationError("Aucun identifiant disponible pour se reconnecter")
        data = await self._http(
            "POST",
            "/authenticate",
            body={"email": self._email, "password": self._password, "parkName": self._park_name},
        )
        return await self._save_tokens(data)

    async def authenticate(self) -> SessionTokens:
        """Connexion initiale explicite ou reconnexion forcee."""
        async with self._auth_lock:
            return await self._authenticate_locked()

    async def _refresh_locked(self) -> SessionTokens:
        if self._tokens is None:
            raise AuthenticationError("Aucun token a renouveler")
        token = (
            self._tokens.refresh_token
            if self._refresh_header_token == "refresh"
            else self._tokens.access_token
        )
        data = await self._http("POST", "/refreshToken", token=token, empty_body=True)
        return await self._save_tokens(data)

    async def refresh(self) -> SessionTokens:
        """Renouvellement manuel; necessite la validation du type de token."""
        async with self._auth_lock:
            return await self._refresh_locked()

    async def _ensure_valid_tokens(self) -> None:
        if self._tokens and not self._tokens.expires_soon():
            return
        async with self._auth_lock:
            if self._tokens and not self._tokens.expires_soon():
                return
            if self._tokens is None:
                await self._authenticate_locked()
                return
            try:
                await self._refresh_locked()
            except AuthenticationError:
                # Reconnexion de secours uniquement si des identifiants ont
                # ete fournis. Une seule tentative, sans boucle.
                await self._authenticate_locked()

    async def _recover_after_401(self, failed_access_token: str) -> None:
        async with self._auth_lock:
            if self._tokens and self._tokens.access_token != failed_access_token:
                return  # Un autre appel a deja rafraichi la session.
            if self._tokens is None:
                await self._authenticate_locked()
                return
            try:
                await self._refresh_locked()
            except AuthenticationError:
                await self._authenticate_locked()

    async def _get(self, path: str) -> object:
        await self._ensure_valid_tokens()
        assert self._tokens is not None
        old_token = self._tokens.access_token
        try:
            return await self._http("GET", path, token=old_token)
        except AuthenticationError:
            await self._recover_after_401(old_token)
            assert self._tokens is not None
            return await self._http("GET", path, token=self._tokens.access_token)

    async def _get_list(self, path: str) -> list[dict[str, Any]]:
        data = await self._get(path)
        if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
            raise ProtocolError(f"Liste JSON attendue sur {path}")
        return data

    async def get_home(self) -> Home:
        """L'endpoint /homes renvoie UN objet dans les captures VAV 4.14.4."""
        data = await self._get("/homes")
        if not isinstance(data, dict):
            raise ProtocolError("Objet JSON attendu sur /homes")
        return Home.from_api(data)

    async def get_hubs(self) -> tuple[Hub, ...]:
        """Ne conserve jamais aesKey, secretKey, wifiPwd ni MAC des hubs."""
        return tuple(Hub.from_api(raw) for raw in await self._get_list("/hubs"))

    async def get_rooms(self) -> tuple[Room, ...]:
        return tuple(Room.from_api(raw) for raw in await self._get_list("/rooms"))

    async def get_devices(self) -> tuple[Device, ...]:
        """Ne conserve jamais les champs `properties` et `temp` (cle Zigbee)."""
        return tuple(Device.from_api(raw) for raw in await self._get_list("/devices"))

    async def get_thermostats(self, hub_id: str) -> tuple[Thermostat, ...]:
        safe_id = quote(str(hub_id), safe="")
        return tuple(
            Thermostat.from_api(raw)
            for raw in await self._get_list(f"/hubs/{safe_id}/local-services")
            if raw.get("type") == "thermostat"
        )

    async def get_snapshot(self) -> Snapshot:
        """Decouverte en lecture seule (4 GET + 1 GET par passerelle)."""
        home = await self.get_home()
        hubs = await self.get_hubs()
        rooms = await self.get_rooms()
        devices = await self.get_devices()
        thermostats: list[Thermostat] = []
        for hub in hubs:
            thermostats.extend(await self.get_thermostats(hub.id))
        return Snapshot.from_parts(home, hubs, rooms, devices, tuple(thermostats))
