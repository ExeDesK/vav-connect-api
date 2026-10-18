"""Jetons de session : validation, rotation et serialisation explicite.

ATTENTION : `to_storage()` contient des secrets. Son retour doit etre sauvegarde
uniquement par l'application appelante, dans un stockage protege.
"""

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

    def __post_init__(self) -> None:
        if not isinstance(self.access_token, str) or not self.access_token:
            raise ProtocolError("Session : access_token invalide")
        if not isinstance(self.refresh_token, str) or not self.refresh_token:
            raise ProtocolError("Session : refresh_token invalide")
        if not isinstance(self.expires_at, datetime) or self.expires_at.tzinfo is None \
                or self.expires_at.utcoffset() is None:
            raise ProtocolError("Session : date d'expiration avec fuseau requise")

    @classmethod
    def from_response(cls, data: dict[str, Any]) -> "SessionTokens":
        """Convertit la reponse JSON de /authenticate ou /refreshToken."""
        if not isinstance(data, dict):
            raise ProtocolError("Session : objet JSON attendu")
        expires_in = data.get("expires_in")
        if isinstance(expires_in, bool) or not isinstance(expires_in, (float, int)) \
                or not 0 < expires_in <= 366 * 86400:
            raise ProtocolError("Session : expires_in invalide")
        return cls(
            access_token=data.get("access_token"),
            refresh_token=data.get("refresh_token"),
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=expires_in),
            home_id=_optional_str(data.get("homeId")),
            park_id=_optional_str(data.get("parkId")),
            user_id=_optional_str(data.get("userId")),
        )

    def expires_soon(self, margin_seconds: int = 300) -> bool:
        if margin_seconds < 0:
            raise ValueError("margin_seconds doit etre positif")
        return self.expires_at <= datetime.now(timezone.utc) + timedelta(seconds=margin_seconds)

    def to_storage(self) -> dict[str, Any]:
        """Serialization explicite. SENSIBLE : inclut les deux jetons en clair."""
        return {
            "schema_version": 1,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.expires_at.astimezone(timezone.utc).isoformat(),
            "home_id": self.home_id,
            "park_id": self.park_id,
            "user_id": self.user_id,
        }

    @classmethod
    def from_storage(cls, data: dict[str, Any]) -> "SessionTokens":
        """Restaure une session; aucun acces reseau ni lecture disque implicites."""
        if not isinstance(data, dict) or type(data.get("schema_version")) is not int \
                or data["schema_version"] != 1:
            raise ProtocolError("Session sauvegardee : schema non pris en charge")
        raw_expiry = data.get("expires_at")
        if not isinstance(raw_expiry, str):
            raise ProtocolError("Session sauvegardee : expiration invalide")
        try:
            expires_at = datetime.fromisoformat(raw_expiry.replace("Z", "+00:00"))
        except ValueError:
            raise ProtocolError("Session sauvegardee : expiration invalide") from None
        return cls(
            access_token=data.get("access_token"),
            refresh_token=data.get("refresh_token"),
            expires_at=expires_at,
            home_id=_optional_str(data.get("home_id")),
            park_id=_optional_str(data.get("park_id")),
            user_id=_optional_str(data.get("user_id")),
        )


def _optional_str(value: object) -> str | None:
    return str(value) if isinstance(value, str) or type(value) is int else None
