"""Exceptions sans contenu HTTP sensible (tokens, secrets, identifiants personnels)."""


class VAVError(Exception):
    """Erreur de la bibliotheque VAV."""


class AuthenticationError(VAVError):
    """Authentification ou renouvellement refuses."""


class TransportError(VAVError):
    """Echec reseau ou timeout."""


class ProtocolError(VAVError):
    """Reponse inattendue de l'API."""


class APIError(VAVError):
    """Erreur HTTP non liee a une authentification."""

    def __init__(self, method: str, path: str, status: int) -> None:
        self.method = method
        self.path = path
        self.status = status
        super().__init__(f"VAV API: HTTP {status} sur {method} {path}")


class RateLimitError(APIError):
    """Le serveur a renvoye HTTP 429."""

    def __init__(self, method: str, path: str, retry_after: str | None = None) -> None:
        self.retry_after = retry_after
        super().__init__(method, path, 429)
