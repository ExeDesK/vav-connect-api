r"""Test manuel NON destructif du refresh Otodo, sans afficher de secrets.

Lance seulement POST /authenticate, GET /homes, POST /refreshToken et GET /homes.
Les tests automatises utilisent un faux serveur local : jamais le cloud reel.

PowerShell (venv active) :
    $env:VAV_EMAIL = Read-Host 'Email VAV'
    $env:VAV_PASSWORD = [System.Net.NetworkCredential]::new('', (Read-Host 'Mot de passe VAV' -AsSecureString)).Password
    try { python .\examples\verify_refresh.py --header-token refresh } finally { Remove-Item Env:\VAV_PASSWORD -ErrorAction SilentlyContinue }
"""

from __future__ import annotations

import argparse
import asyncio
import os
from typing import Literal

from vav_connect import (
    APIError,
    AuthenticationError,
    ProtocolError,
    RateLimitError,
    TransportError,
    VAVClient,
)
from vav_connect.client import DEFAULT_BASE_URL


async def probe_refresh(
    email: str,
    password: str,
    *,
    header_token: Literal["refresh", "access"] = "refresh",
    base_url: str = DEFAULT_BASE_URL,
) -> int:
    """Execute une seule tentative de refresh, sans reauthentification de secours.

    `base_url` n'est expose que pour les tests sur un faux serveur local.
    Aucune valeur de jeton, corps HTTP ou identifiant de logement n'est affichee.
    """
    step = "authentification initiale"
    print("=== Diagnostic VAV Connect : refresh (lecture seule) ===")
    print(f"Jeton teste dans l'en-tete token : {header_token}")
    try:
        async with VAVClient(
            email,
            password,
            refresh_header_token=header_token,
            base_url=base_url,
        ) as client:
            await client.authenticate()
            print("[1/4] POST /authenticate : OK")

            step = "lecture avant renouvellement"
            # Requete brute securisee, sans retry automatique, pour isoler ce test.
            await client._http("GET", "/homes", token=client.tokens.access_token)
            print("[2/4] GET /homes (avant) : OK")

            assert client.tokens is not None
            previous_access = client.tokens.access_token
            previous_refresh = client.tokens.refresh_token

            step = "renouvellement du token"
            updated = await client.refresh()  # Appel explicite : PAS de fallback login
            print("[3/4] POST /refreshToken : OK")
            print("      Nouveau access_token recu : oui")
            print("      Nouveau refresh_token recu : oui")
            print(f"      Access token different : {'oui' if previous_access != updated.access_token else 'non'}")
            print(f"      Refresh token different : {'oui' if previous_refresh != updated.refresh_token else 'non'}")

            step = "lecture apres renouvellement"
            # Evite le second refresh automatique que VAVClient._get() ferait
            # en cas de HTTP 401, afin de ne faire qu'une seule tentative.
            await client._http("GET", "/homes", token=updated.access_token)
            print("[4/4] GET /homes (apres) : OK")

        print("RESULTAT : refresh valide et nouveau token accepte pour la lecture.")
        return 0
    except AuthenticationError:
        print(f"ECHEC a l'etape '{step}' : HTTP 401/403 (authentification refusee).")
        print("Aucune reconnexion automatique ne masque cet echec du refresh.")
        return 2
    except RateLimitError:
        print(f"ECHEC a l'etape '{step}' : HTTP 429 (limitation du serveur).")
        print("Arreter les essais repetes et reessayer plus tard.")
        return 3
    except APIError as error:
        print(f"ECHEC a l'etape '{step}' : HTTP {error.status}.")
        return 3
    except (TransportError, ProtocolError) as error:
        print(f"ECHEC a l'etape '{step}' : {type(error).__name__}.")
        return 3
    except Exception as error:
        # Par defaut, n'afficher aucun message d'exception potentiellement sensible.
        print(f"ECHEC inattendu a l'etape '{step}' : {type(error).__name__}.")
        return 4


def main() -> int:
    parser = argparse.ArgumentParser(description="Test du refresh VAV, sans aucune commande de chauffage")
    parser.add_argument(
        "--header-token", choices=("refresh", "access"), default="refresh",
        help="Jeton a mettre dans le header token du POST /refreshToken (defaut : refresh)",
    )
    args = parser.parse_args()

    email = os.getenv("VAV_EMAIL")
    password = os.getenv("VAV_PASSWORD")
    if not email or not password:
        print("Definir VAV_EMAIL et VAV_PASSWORD dans l'environnement avant le test.")
        return 1
    return asyncio.run(probe_refresh(email, password, header_token=args.header_token))


if __name__ == "__main__":
    raise SystemExit(main())
