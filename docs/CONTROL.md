# Contrôles VAV : SDK 0.3.0 alpha (opt-in)

Les opérations HTTP ont été vérifiées par un banc d'essai manuel sur un compte VAV autorisé. **Les nouvelles méthodes SDK de la v0.3.0 ont uniquement été testées sur un faux serveur local**. Home Assistant/HACS sera un dépôt distinct ; aucun serveur REST n'est nécessaire.

## Double accord requis

Le client est toujours en lecture seule par défaut. Toute méthode de contrôle appelée **sans `apply=True`** produit un `ControlResult` d'**aperçu** et n'effectue aucune mutation. Pour exécuter une commande, activer aussi `VAVClient(allow_writes=True)`. Le SDK n'affiche pas de confirmation interactive ; l'application appelante doit en gérer une.

```python
import os
from vav_connect import VAVClient, WorkingMode

async with VAVClient(os.environ["VAV_EMAIL"], os.environ["VAV_PASSWORD"]) as client:
    zone = (await client.get_snapshot()).zones[0]
    preview = await client.set_working_mode(zone.thermostat_id, WorkingMode.ECO)
    for change in preview.changes:
        print(change.field, change.before, "->", change.after)
    assert not preview.applied

# Ecriture réelle UNIQUEMENT après contrôle de l'absence d'effacement dans VAV :
# async with VAVClient(..., allow_writes=True) as client:
#     await client.set_working_mode(zone.thermostat_id, WorkingMode.ECO, apply=True)
```

## API publique

| Méthode asynchrone | Action |
|---|---|
| `set_working_mode(thermostat_id, WorkingMode.COMFORT_MINUS_TWO, apply=False)` | Mode individuel 0 à 6 |
| `set_comfort_temperature(thermostat_id, 20.5, apply=False)` | Consigne Confort, pas de 0,5 °C |
| `set_weekly_schedule(thermostat_id, events, apply=False)` | Remplace tout le programme hebdomadaire |
| `replace_schedule_days(thermostat_id, {0: monday_events}, apply=False)` | Remplace uniquement certains jours |
| `set_presence(False, apply=False)` | Passage Absence : PATCH maison, PUT Éco par zone |
| `set_presence(True, apply=False)` | Présence : PATCH maison, PUT Auto par zone |
| `set_holidays(until=aware_datetime, pilot_mode=PilotMode.FROST_PROTECTION, apply=False)` | Vacances : PUT par zone, maison inchangée |
| `cancel_holidays(apply=False)` | Retour Auto + Présence, reprise partielle possible |

Les identifiants proviennent de `snapshot.zones[].thermostat_id`. L'indice `d=0` est **lundi**, `d=6` est dimanche. `WeekEvent(day_index, minute_of_week, PilotMode.X)` emploie une minute absolue : mardi 22:00 = 2760. Les codes `PilotMode` ne sont PAS les `WorkingMode`.

```python
from vav_connect import WeekEvent, PilotMode
monday = [
    WeekEvent(0, 480, PilotMode.COMFORT), # 08:00
    WeekEvent(0, 540, PilotMode.ECO), # 09:00
    WeekEvent(0, 1140, PilotMode.COMFORT), # 19:00
]
preview = await client.replace_schedule_days(thermostat_id, {0: monday})
# Pour envoyer : allow_writes=True et apply=True, après contrôle manuel.
```

Vacances : `pilot_mode=ECO (mm=3)`, `FROST_PROTECTION (mm=8)` ou `OFF (mm=0)`. `until` exige un `datetime` avec fuseau horaire explicite, situé plus de dix minutes dans le futur. L'API reçoit un timestamp UTC.

## Protections et limites

- **Effacement :** `loadShedding` doit être explicitement `false` pour chaque zone ; **cela ne garantit pas l'absence de modulation énergétique**. Consulter indépendamment VAV et ne pas commander pendant un effacement.
- PUT des thermostats : objet complet relu récemment, modification limitée aux champs autorisés, comparaison immédiatement avant écriture, contrôle GET après. Une concurrence entre dernière lecture et PUT reste possible sans If-Match/ETag côté Otodo.
- Scénarios globaux séquentiels et **non atomiques**. `PartialWriteError.completed` contient les étapes vérifiées ; `uncertain_target` l'étape en erreur. Ne pas relancer à l'aveugle ; relire logement et cinq zones puis vérifier dans l'application VAV officielle.
- **Aucun retry** de PUT ou PATCH : un timeout peut survenir après l'application de la commande. `WriteUncertainError` signifie qu'il faut d'abord observer l'état réel.
- Le serveur peut garder `holidays` même après désactivation ; seul `workingMode == 7` signifie Vacances activé. Annuler Vacances renvoie les zones à Auto et remet `isAtHome=true` sans effacer nécessairement les métadonnées historiques.
- Les champs sensibles Zigbee, Wi-Fi, tokens ne sont ni inclus dans les `ControlResult`, ni loggés. Le PUT contient le service thermostat complet car une écriture partielle n'a pas été validée ; ces objets ne doivent pas être affichés ni sauvegardés.
