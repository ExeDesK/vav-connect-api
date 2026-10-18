# vav-connect-api

**SDK Python asynchrone, communautaire et non officiel pour VAV Connect / Otodo.**

**Version 0.1.1 — alpha, lecture seule.** Le code repose sur les echanges HTTPS observes dans VAV Android 4.14.4. Les lectures ont ete **validees sur un compte autorise reel** ; le renouvellement des tokens reste a verifier. Ce n'est pas une integration HACS ; celle-ci sera developpee dans un depot separe (`ha-vav-connect`).

Le projet ne modifie ni la passerelle, ni l'appairage, ni la configuration d'effacement electrique. Il ne transmet aucune commande aux radiateurs : les **seuls POST autorises** sont la connexion (`/authenticate`) et le renouvellement de session (`/refreshToken`).

## Pourquoi Python et pas TypeScript / JavaScript ?

Nous avons retenu **Python pour la branche principale**, parce que l'objectif prioritaire est une integration native Home Assistant :

- Home Assistant execute ses integrations en Python. Un SDK Python asynchrone (`aiohttp`) peut etre importe directement dans l'integration HACS et reutiliser sa session HTTP, sans serveur intermediaire.
- Une seule pile runtime simplifie l'installation, le diagnostic, la gestion des identifiants et la maintenance sur Home Assistant OS, Container et Core.
- La bibliotheque Python reste independante de Home Assistant et exploitable dans un script, un outil CLI ou un autre projet Python.
- C'est un **choix de deploiement et de maintenance**, pas une limite technique de l'API Otodo, qui parle HTTPS/JSON et convient tout autant a TypeScript.

**TypeScript reste pertinent pour une API REST autonome** : typage partage avec les clients web, ecosysteme npm, Fastify et integration facile dans des outils comme n8n. Nous prevoyons donc une branche Git **`ts/rest`** pour explorer cette alternative sans introduire de dependances Node.js dans `main`. Cette branche est d'abord un espace d'experimentation, **pas une deuxieme API deja fonctionnelle**. Si une variante TypeScript/REST devient un produit maintenu et publie, il sera preferable de la transformer en paquet ou depot autonome plutot que d'entretenir deux implementations divergentes dans des branches permanentes.

**Architecture visee :** `ha-vav-connect` (HACS, Python) → `vav-connect-api` (ce SDK) → cloud Otodo → passerelle VAV existante. L'eventuel serveur REST est **optionnel**, jamais requis par HACS.

## Fonctionnalites v0.1.1

- `POST /authenticate` avec `email`, `password`, `parkName=vav`.
- `POST /refreshToken` **sans body**, avec header `token`, rotation des tokens et expiration prise en compte.
- Renouvellement preventif (5 minutes avant expiration), sur HTTP 401 et une seule nouvelle tentative de lecture ; reconnexion possible si les identifiants sont disponibles.
- Lecture `GET /homes`, `/hubs`, `/rooms`, `/devices`, `/hubs/{hubId}/local-services`.
- Modeles Python immuables pour les logements, pieces, passerelles, capteurs, modules, thermostats, horaires et vacances.
- Lecture des temperatures (Kelvin x10 → °C), humidite, batterie, connectivite et puissance ; association thermostat ↔ capteur/module.
- Exposition de la valeur kWh **sans la qualifier de compteur cumulatif** : sa semantique temporelle n'est pas encore etablie.
- Exclusion volontaire des proprietes et secrets Zigbee, des mots de passe de passerelle et des metadonnees personnelles non necessaires.
- Rate limit HTTP 429 remonte a l'appelant, sans flood de requetes.

### Important : type de token de refresh encore a valider sur un compte reel

La capture **confirme** : `POST https://api.gateway.otodo.io/refreshToken`, body vide, header `token: ...`, reponse contenant `access_token`, `refresh_token` et `expires_in=2592000` (30 jours). En revanche, l'en-tete etait masque dans la capture : **nous ne savons pas avec certitude** s'il contenait l'`access_token` ou le `refresh_token` precedent.

Par defaut le SDK utilise le **refresh token** (hypothese logique, mais non confirmee). Si une capture ulterieure montre qu'Otodo utilise l'access token, choisir `refresh_header_token="access"`. Avec login et mot de passe, un echec d'authentification au refresh declenche au maximum une reconnexion par les identifiants ; sans identifiants sauvegardes, une erreur est remontee.

## Installation locale (Windows / PowerShell)

Python **3.11+** :

```powershell
cd .\vav-connect-api
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest -q
```

L'installation editable ne publie rien sur PyPI. Aucune cle ni identifiant de production ne doit etre place dans le code ou les tests.

### Premier exemple : lecture seule

```powershell
$env:VAV_EMAIL = "mon-adresse@example.com"
$env:VAV_PASSWORD = "mon-mot-de-passe"
python .\examples\inspect_account.py
```

Ou dans du code Python :

```python
import asyncio
from vav_connect import VAVClient, WorkingMode

async def main():
    async with VAVClient("email@example.com", "mot-de-passe") as client:
        snapshot = await client.get_snapshot()
        print("Present :", snapshot.home.is_at_home)
        for zone in snapshot.zones:
            mode = zone.thermostat.working_mode
            print(zone.name, zone.temperature_c, mode == WorkingMode.AUTO)

asyncio.run(main())
```

`get_snapshot()` fait les lectures necessaires une fois (quatre GET + un GET par passerelle). Il ne lance pas de polling automatique. L'exemple n'imprime pas de tokens ni de cle Zigbee.

### Tokens et securite

Par defaut, les tokens sont conserves **uniquement en memoire** et ne sont pas enregistres sur disque. Les champs secrets de `SessionTokens` ne figurent pas dans son `repr`. Pour une integration HA future, le `token_callback` asynchrone pourra sauvegarder les nouveaux tokens dans un stockage **protege** (la bibliotheque ne propose pas elle-meme de chiffrement). **Ne jamais logger `client.tokens.access_token`, `refresh_token`, les requetes brutes ou les fichiers captures.**

L'import d'une session precedente est possible avec `VAVClient(tokens=ma_session)`. Fournir egalement `email/password` est facultatif pour une reconnexion de secours.

Le polling dans Home Assistant devra etre raisonnable (par exemple 60–120 s, ajustable) : les quotas du cloud n'ont pas ete documentes. L'integration HA n'est pas fournie dans cette livraison.

## Comprendre les modes

**Mode global (`thermostat.working_mode`)** :

| Valeur | Signification |
|---:|---|
| 0 | Auto |
| 1 | Confort |
| 2 | Confort -1 °C |
| 3 | Confort -2 °C |
| 4 | Eco |
| 5 | Hors gel |
| 6 | Arret |
| 7 | Vacances |

**Ordre fil pilote** (`weeklyEvents.mm`, `holidays.mm` et capacite 6 du module) :

| Valeur | Signification |
|---:|---|
| 0 | Arret |
| 2 | Confort |
| 3 | Eco |
| 8 | Hors gel |
| 9 | Confort -1 °C |
| 10 | Confort -2 °C |

Il ne faut jamais melanger ces deux systemes de codes. En vacances : `workingMode=7` et `holidays={until: date UTC, mm: 3|8|0}`. `weeklyEvents.t` est interprete comme une minute absolue dans la semaine (`1440*d + minute du jour`) ; le jour civil correspondant a `d=0` reste a confirmer.

Voir [`docs/PROTOCOL.md`](docs/PROTOCOL.md) pour les observations, incertitudes et futures commandes.

## Test reel du renouvellement (sans ecriture de chauffage)

Les premieres lectures reelles de logement, passerelle et thermostats ont reussi ; le refresh reste le point a verifier.

Le script `examples/verify_refresh.py` force un refresh **une seule fois**, sans attendre l'expiration : connexion, GET `/homes`, POST `/refreshToken`, puis GET `/homes` avec le nouveau token. Il n'affiche aucun secret, ne sauvegarde aucun jeton et ne tente pas silencieusement une nouvelle connexion si le refresh est refuse.

Dans PowerShell (venv active), utiliser :

```powershell
$env:VAV_EMAIL = Read-Host "Email VAV"
$env:VAV_PASSWORD = [System.Net.NetworkCredential]::new("", (Read-Host "Mot de passe VAV" -AsSecureString)).Password
try {
    python .\examples\verify_refresh.py --header-token refresh
} finally {
    Remove-Item Env:\VAV_PASSWORD -ErrorAction SilentlyContinue
}
```

Si le refresh renvoie une erreur HTTP 401/403, **ne pas repeter en boucle** : essayer ensuite la variante `--header-token access` (une nouvelle connexion est necessaire). Les deux variantes ne doivent pas etre lancees automatiquement. Voir [`docs/LIVE_REFRESH_TEST.md`](docs/LIVE_REFRESH_TEST.md) pour les resultats attendus et precautions.

Les tests automatiques emploient exclusivement un faux serveur local. Les commandes `PUT` sont absentes de cette version, et les fonctions d'effacement restent gerees par VAV.

**Les commandes `PUT` sont volontairement absentes de cette version.** L'application Android envoie des objets thermostat presque complets via `PUT /hubs/{hubId}/local-services/{serviceId}` ; nous ne savons pas si les mises a jour partielles sont acceptees, et un objet perime pourrait ecraser `loadShedding` ou une programmation. Le pilote ne sera ajoute qu'apres validation de la securite des mises a jour et du comportement pendant un effacement electrique.

## Git et branche `ts/rest`

Une archive Git bundle (`vav-connect-api-branches.bundle`) accompagne la livraison et conserve les branches `main` et `ts/rest`. Clonage :

```powershell
git clone .\vav-connect-api-branches.bundle vav-connect-api
git -C .\vav-connect-api branch --all
git -C .\vav-connect-api switch ts/rest  # espace de recherche TS/REST
```

Pour publier sur GitHub, creer d'abord un **depot vide** (sans README genere), puis renseigner son URL :

```powershell
git remote add origin https://github.com/VOTRE_COMPTE/vav-connect-api.git
git push -u origin main
git push -u origin ts/rest
```

Ne jamais publier de captures reelles ou de fichiers contenant des tokens. La branche TypeScript n'est qu'un prototype documentaire a ce stade, sans serveur Node.js fonctionnel.

## Statut, projet et licence

- [`VERSIONS.md`](VERSIONS.md) : historique des versions.
- [`CONTEXT.md`](CONTEXT.md) : decisions prises, hypotheses et etapes suivantes.
- [`AGENTS.md`](AGENTS.md) : regles de contribution et tests obligatoires.
- [`docs/PROTOCOL.md`](docs/PROTOCOL.md) : routes et formats traces.
- Tests : `python -m pytest -q`, sans reseau Otodo (serveur HTTP simule en local).
- Licence : [MIT](LICENSE).

**Projet communautaire non officiel, sans affiliation ni validation par VAV, Otodo ou un operateur d'effacement.**
