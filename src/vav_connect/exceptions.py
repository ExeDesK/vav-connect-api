"""Exceptions publiques : jamais de corps HTTP ou valeurs de tokens."""


class VAVError(Exception):
    """Erreur de la bibliotheque VAV."""


class AuthenticationError(VAVError):
    """Jeton invalide ou renouvellement refuse (HTTP 401)."""


class TransportError(VAVError):
    """Echec reseau ou timeout."""


class ProtocolError(VAVError):
    """Reponse inattendue ou format non pris en charge."""


class TokenPersistenceError(VAVError):
    """Session renouee en memoire, mais sauvegarde par callback echouee."""


class APIError(VAVError):
    """Erreur HTTP non liee a une authentification."""

    def __init__(self, method: str, path: str, status: int) -> None:
        self.method = method
        self.path = path
        self.status = status
        super().__init__(f"VAV API: HTTP {status} sur {method} {path}")


class ForbiddenError(APIError):
    """Acces interdit (HTTP 403) : ne pas rafraichir les jetons automatiquement."""

    def __init__(self, method: str, path: str) -> None:
        super().__init__(method, path, 403)


class RateLimitError(APIError):
    """Quota HTTP 429 : aucune tentative automatique supplementaire."""

    def __init__(self, method: str, path: str, retry_after: str | None = None) -> None:
        self.retry_after = retry_after
        super().__init__(method, path, 429)

    @property
    def retry_after_seconds(self) -> float | None:
        """Delai suggere (seconds ou date HTTP), sans attente implicite."""
        if not self.retry_after:
            return None
        from datetime import datetime, timezone
        from email.utils import parsedate_to_datetime

        try:
            seconds = float(self.retry_after)
            if seconds >= 0 and seconds != float("inf"):
                return seconds
            return None
        except ValueError:
            pass
        try:
            future = parsedate_to_datetime(self.retry_after)
            if future.tzinfo is None:
                return None
            return max(0.0, (future - datetime.now(timezone.utc)).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None
