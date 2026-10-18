"""Safe preview only: this example NEVER enables writes."""
import asyncio
import os

from vav_connect import VAVClient, WorkingMode


async def main() -> None:
    async with VAVClient(os.environ["VAV_EMAIL"], os.environ["VAV_PASSWORD"]) as client:
        snapshot = await client.get_snapshot()
        if not snapshot.zones:
            print("No thermostat found")
            return
        zone = snapshot.zones[0]
        plan = await client.set_working_mode(zone.thermostat_id, WorkingMode.AUTO)
        print("PREVIEW ONLY", zone.name, "changes", len(plan.changes))
        for change in plan.changes:
            print(change.field, change.before, "->", change.after)
        assert plan.applied is False


if __name__ == "__main__":
    asyncio.run(main())
