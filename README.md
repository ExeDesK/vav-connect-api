# vav-connect-api

**SDK Python asynchrone, communautaire et non officiel pour VAV Connect / Otodo.**

**Version 0.3.0 — alpha, lecture seule par défaut ; commandes opt-in.** Les lectures et le renouvellement de session ont été validés sur un compte autorisé réel le 18 octobre 2026. Cette bibliothèque est indépendante de Home Assistant : la future intégration HACS sera hébergée dans un dépôt distinct, `ha-vav-connect`.

> **Préserver VAV et l'effacement électrique.** Les commandes exigent `allow_writes=True` **et** `apply=True` ; aucune écriture par défaut. Ne jamais désappairer la passerelle ni écrire `loadShedding`. Le booléen `loadShedding=false` ne garantit pas qu'aucun effacement électrique soit en cours ; vérifier indépendamment avant tout pilotage.

## Pourquoi Python plutôt que TypeScript / JavaScript ?

Le choix de **Python pour `main`** découle de notre cible principale : **une intégration Home Assistant native, simple à installer via HACS**.

- Les intégrations Home Assistant sont des composants Python. Notre SDK asynchrone basé sur `aiohttp` peut être importé directement et utiliser une session HTTP fournie par Home Assistant, sans conteneur Node.js supplémentaire ni serveur REST intermédiaire.
- Une seule pile réduit le nombre de services à maintenir et simplifie déploiement, journalisation, authentification, traitement des erreurs et dépannage.
- Le SDK est **indépendant de Home Assistant** : il fonctionne aussi dans des scripts ou services Python et pourra être publié sur PyPI.
- **Ce n'est pas une contrainte du protocole Otodo** : son interface HTTPS/JSON pourrait tout aussi bien être consommée depuis TypeScript.

Un **SDK TypeScript et une API REST Fastify** seraient pertinents pour une utilisation depuis le web, Node.js, n8n ou d'autres langages. Une branche expérimentale **`ts/rest` est envisagée plus tard**, mais **n'existe pas dans le dépôt GitHub actuel** ; sa création a été volontairement reportée. Si la variante REST devient un produit maintenu, un dépôt ou paquet séparé sera probablement plus sain qu'une branche Git permanente.

**Architecture cible :** `ha-vav-connect` (HACS/Python) → `vav-connect-api` (ce SDK) → API cloud Otodo → passerelle VAV d'origine.

## Fonctionnalités de v0.3.0

- Authentification initiale : `POST /authenticate`, `parkName=vav`.
- Refresh **confirmé sur le cloud réel** : `POST /refreshToken` sans corps, en-tête `token: <refresh_token>`. **Les deux jetons changent** à chaque renouvellement réussi ; le nouvel `access_token` a été testé sur `GET /homes`.
- Expiration avec marge de sécurité de 5 minutes, refresh préventif, reprise contrôlée sur `401`, verrouillage des renouvellements concurrents.
- Sérialisation/restauration explicites des jetons (`SessionTokens.to_storage()` / `from_storage()`), sans sauvegarde disque automatique ; callback asynchrone pour la persistance gérée par le client.
- Résilience limitée aux **GET** : une relance par défaut sur erreur de transport ou HTTP `408/500/502/503/504`, temporisation courte et configurable. **Pas de retry automatique de `POST` ou de HTTP `429`.**
- Distinction entre `401` (nouveau refresh envisageable), `403` (accès interdit sans refresh) et `429` (quota, délai `Retry-After` exposé). Redirections HTTP désactivées pour éviter la propagation du header secret `token`.
- Lecture de `/homes`, `/hubs`, `/rooms`, `/devices`, `/hubs/{hubId}/local-services` et `/health` (état du **cloud**, pas état des radiateurs).
- Modèles immuables, projection sans secrets Zigbee/Wi-Fi ni métadonnées personnelles inutiles, reconnaissance des 8 modes thermostat, ordres fil pilote, vacances et événements hebdomadaires.
- Propriétés dérivées par zone : température, consigne Confort, humidité, batterie, connectivité, puissance. La mesure kWh est disponible **sans hypothèse de cumul**.
- **83 tests automatisés locaux** sans contact avec le cloud Otodo.
- **Commandes optionnelles** : modes, Confort, calendrier, Présence/Absence, Vacances et annulation. Un `PATCH /homes/{id}` ou un `PUT /hubs/{hubId}/local-services/{serviceId}` n'est possible qu'après double opt-in. Pas de retry automatique des écritures.

## Installer et tester (Windows / PowerShell)

Prérequis : **Python 3.11+** et Git.

```powershell
cd .\vav-connect-api  # depuis le repertoire parent du depot
py -m venv .venv            # uniquement si le venv n'existe pas
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest -q
```

Le nom de dossier est indicatif. Les tests ne déclenchent aucune écriture de chauffage ; ils parlent exclusivement à un serveur HTTP simulé sur `127.0.0.1`.

### Premier test sur son installation

```powershell
$env:VAV_EMAIL = Read-Host "Email VAV"
$env:VAV_PASSWORD = [System.Net.NetworkCredential]::new(
    "", (Read-Host "Mot de passe VAV" -AsSecureString)
).Password
try {
    python .\examples\inspect_account.py
} finally {
    Remove-Item Env:\VAV_PASSWORD -ErrorAction SilentlyContinue
}
```

Ne publiez **jamais** les identifiants, jetons, captures HTTP, clés Zigbee, informations de point de livraison électrique ou sauvegardes de session sur GitHub. Les fichiers `tests/` n'emploient que des données synthétiques.

### Depuis un script Python

```python
import asyncio
from vav_connect import VAVClient, WorkingMode

async def main():
    async with VAVClient("email@example.com", "mot-de-passe") as client:
        snapshot = await client.get_snapshot()
        print("Présent :", snapshot.home.is_at_home)
        for zone in snapshot.zones:
            print(zone.name, zone.temperature_c, zone.comfort_temperature_c,
                  zone.working_mode == WorkingMode.AUTO)

asyncio.run(main())
```

Les valeurs de cet exemple sont des placeholders, pas de vrais identifiants. `get_snapshot()` effectue **4 GET plus 1 GET par passerelle**, sans surveillance en tâche de fond. Pour HA, prévoir une actualisation mesurée (par exemple 60–120 secondes, ajustable) : les limites d'API Otodo sont inconnues.

## Conserver la session entre redémarrages

Le SDK conserve les jetons **en mémoire uniquement**. Pour une application qui doit survivre à un redémarrage, l'appelant peut fournir un `token_callback` asynchrone, qui sauvegardera **les deux nouveaux jetons** de façon atomique après chaque connexion ou refresh. En cas d'échec de cette sauvegarde, une `TokenPersistenceError` est levée ; le SDK garde néanmoins les nouveaux jetons en mémoire pour ne pas revenir à une paire potentiellement invalidée.

`SessionTokens.to_storage()` renvoie **des secrets en clair**. Il n'y a volontairement **pas d'écriture sur disque, de chiffrement ou de gestion de secret fournis par le SDK**. C'est à l'intégration appelante d'utiliser son stockage confidentiel, d'en contrôler les permissions et d'éviter tout affichage du dictionnaire. `SessionTokens.from_storage()` permet de réhydrater la session avant de créer `VAVClient(tokens=...)`.

La sauvegarde atomique est particulièrement importante : le refresh **fait tourner le `refresh_token`**. Voir [`docs/RESILIENCE.md`](docs/RESILIENCE.md) pour la politique d'authentification, de reprise et de confidentialité.

## Modes thermostat et fil pilote

Ces deux énumérations sont distinctes :

| `workingMode` | Mode thermostat |
|---:|---|
| 0 | Auto |
| 1 | Confort |
| 2 | Confort -1 °C |
| 3 | Confort -2 °C |
| 4 | Éco |
| 5 | Hors gel |
| 6 | Arrêt |
| 7 | Vacances |

| `weeklyEvents.mm` / `holidays.mm` | Ordre fil pilote |
|---:|---|
| 0 | Arrêt |
| 2 | Confort |
| 3 | Éco |
| 8 | Hors gel |
| 9 | Confort -1 °C |
| 10 | Confort -2 °C |

Pendant les vacances, `workingMode=7` et `holidays` contient une date ISO-UTC et un mode `mm` (`3` Éco, `8` Hors gel, `0` Arrêt). Le tableau `weeklyEvents` utilise `d` (indice 0..6), `t` (minute absolue depuis le début de la semaine) et `mm` (ordre fil pilote). **`d=0` correspond au lundi** (confirmé dans VAV) ; `d=6` au dimanche.

Les méthodes `thermostat.events_for_day(d)`, `zone.humidity_pct`, `zone.battery_pct`, `zone.power_w`, etc., sont des accès **en lecture seule** à ces données.

## Contrôler VAV en v0.3.0

Le SDK est **lecture seule par défaut**. Un appel de commande sans `apply=True` ne fait qu'un aperçu, même si les écritures sont autorisées. Le SDK ne propose aucun serveur REST.

```python
import asyncio, os
from vav_connect import VAVClient, WorkingMode

async def main():
    async with VAVClient(os.environ["VAV_EMAIL"], os.environ["VAV_PASSWORD"]) as client:
        zone = (await client.get_snapshot()).zones[0]
        plan = await client.set_working_mode(zone.thermostat_id, WorkingMode.COMFORT_MINUS_TWO)
        print(plan.changes, plan.applied)  # aperçu uniquement
        # Pour l'écriture réelle (après vérification VAV hors effacement) :
        # VAVClient(..., allow_writes=True), ET set_working_mode(..., apply=True)

asyncio.run(main())
```

Voir [docs/CONTROL.md](docs/CONTROL.md) pour la programmation des jours (lundi=0), les scénarios globaux, les retours et les exceptions. Les contrôles HTTP ont été **validés manuellement en conditions réelles via un banc d'essai séparé**, mais les nouvelles méthodes SDK v0.3.0 ne sont **pas encore validées elles-mêmes** sur Otodo réel ; les tests automatisés utilisent un faux serveur local.

### Limites et sécurité

- Les opérations globales ne sont **pas atomiques**. Une panne au milieu peut laisser un logement en Présence/Absence avec seulement certaines zones modifiées ; ne pas relancer automatiquement.
- Avant un PUT, le service est relu et seuls les champs autorisés sont changés. **Sans ETag / contrôle de version côté serveur, un conflit reste possible entre la dernière lecture et l'écriture**.
- Le SDK refuse un `loadShedding` autre que `false`, mais cela **ne prouve pas** l'absence d'une modulation réseau active. Ne pas piloter pendant un effacement/intervention VAV.
- Otodo peut conserver `holidays` en base après retour Auto : `workingMode==7` seul indique des vacances actives. Le retour Présence force Auto, sans restaurer le mode précédent.
- Pas encore de cache HTTP 304, WebSocket ou interprétation validée de la nature cumulative des données kWh.

## Documentation, développement et publication

- [`docs/PROTOCOL.md`](docs/PROTOCOL.md) : protocole observé et limites.
- [`docs/CONTROL.md`](docs/CONTROL.md) : procédures et risques des commandes.
- [`docs/RESILIENCE.md`](docs/RESILIENCE.md) : persistance des jetons, erreurs HTTP et garde-fous.
- [`docs/LIVE_REFRESH_TEST.md`](docs/LIVE_REFRESH_TEST.md) : compte rendu du refresh réel et diagnostic facultatif.
- [`VERSIONS.md`](VERSIONS.md) : versions.
- [`CONTEXT.md`](CONTEXT.md) : décisions et suite prévue.
- [`AGENTS.md`](AGENTS.md) : règles de contribution.

CI GitHub Actions : tests Python 3.11, 3.12, 3.13 + construction du paquet. **Aucune publication PyPI automatique** n'est configurée et aucune variable secrète n'est nécessaire.

**Projet communautaire non officiel, sans affiliation ni validation par VAV, Otodo ou un opérateur d'effacement électrique.** Licence : [MIT](LICENSE).
