"""Modeles de session sans representation accidentelle des secrets."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from .exceptions import ProtocolError


@dataclass(frozen=True, slots=True)
class SessionTokens:
    access_token: str = field(repr=False)
    refresh_token: str = field(repr=False)
    expires_at: datetime
    home_id: str | None = None
    park_id: str | None = None
    user_id: str | None = None

    @classmethod
    def from_response(cls, data: dict[str, Any]) -> "SessionTokens":
        access = data.get("access_token")
        refresh = data.get("refresh_token")
        expires_in = data.get("expires_in")
        if not isinstance(access, str) or not access:
            raise ProtocolError("Authentification: access_token absent ou invalide")
        if not isinstance(refresh, str) or not refresh:
            raise ProtocolError("Authentification: refresh_token absent ou invalide")
        if isinstance(expires_in, bool) or not isinstance(expires_in, (float, int)) or expires_in <= 0:
            raise ProtocolError("Authentification: expires_in absent ou invalide")
        return cls(
            access_token=access,
            refresh_token=refresh,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
            home_id=_optional_str(data.get("homeId")),
            park_id=_optional_str(data.get("parkId")),
            user_id=_optional_str(data.get("userId")),
        )

    def expires_soon(self, margin_seconds: int = 300) -> bool:
        return self.expires_at <= datetime.now(timezone.utc) + timedelta(seconds=margin_seconds)


def _optional_str(value: object) -> str | None:
    return str(value) if value is not None else None
