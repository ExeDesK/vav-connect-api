r"""Usage sans commande d'ecriture et sans affichage de secrets.

PowerShell :
  $env:VAV_EMAIL="vous@example.com"
  $env:VAV_PASSWORD="..."
  python .\examples\inspect_account.py
"""

import asyncio
import os

from vav_connect import VAVClient


async def main() -> None:
    email = os.environ.get("VAV_EMAIL")
    password = os.environ.get("VAV_PASSWORD")
    if not email or not password:
        raise SystemExit("Definir VAV_EMAIL et VAV_PASSWORD dans l'environnement")

    async with VAVClient(email, password) as client:
        snapshot = await client.get_snapshot()
        print(f"Logement actif : {snapshot.home.is_activated}")
        print(f"A domicile : {snapshot.home.is_at_home}")
        print(f"Passerelles : {len(snapshot.hubs)} | zones : {len(snapshot.zones)}")
        for zone in snapshot.zones:
            print(
                f"- {zone.name}: {zone.temperature_c} °C, "
                f"confort={zone.thermostat.comfort_temperature_c} °C, "
                f"mode={zone.thermostat.working_mode}, "
                f"pilote={zone.pilot_mode}"
            )


if __name__ == "__main__":
    asyncio.run(main())
