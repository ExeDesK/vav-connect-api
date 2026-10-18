# CONTEXT — vav-connect-api

## Objectif

SDK Python indépendant, asynchrone, pour VAV Connect/Otodo. L'intégration native Home Assistant HACS `ha-vav-connect` vivra dans un **deuxième dépôt**. Conserver la passerelle existante connectée, appairée et active dans les dispositifs d'effacement du réseau électrique.

## Décisions confirmées au 18 octobre 2026

- `main` : Python 3.11+, `aiohttp`, dataclasses immuables. Motivation documentée dans `README.md`. Version courante : **0.2.0 alpha**.
- Une expérience TS/REST (TypeScript/Fastify) est envisagée **ultérieurement** ; l'utilisateur a explicitement reporté la création de la branche `ts/rest`. Le dépôt courant ne doit pas supposer cette branche existante.
- Lecture seule : ni PUT, ni PATCH, ni DELETE, ni POST modifiant les thermostats ou l'état du logement. Seuls POST login et refresh autorisés.
- `POST /authenticate` avec email/password/parkName; `POST /refreshToken` sans body et `token: <refresh_token>`.
- **Validation réelle du refresh réussie** : nouveaux access et refresh tokens différents des précédents, suivis d'un GET `/homes` accepté avec le nouvel access token. Ne plus présenter le type de jeton de refresh comme une hypothèse.
- **Premier test réel de lecture réussi** : un logement, une passerelle et cinq zones, températures et modes correctement interprétés. Ne pas publier les identifiants de ressources ni les données personnelles de ce test.
- Tokens seulement en mémoire dans le SDK ; sérialisation explicite si l'application appelante possède un stockage confidentiel. Les deux jetons tournent : une persistance cohérente est importante.
- GET en reprise bornée sur erreurs transitoires, pas de retries POST/429, 403 != 401, redirections interdits pour protéger le header `token`.
- CI : tests entièrement synthétiques sur faux backend local, aucune variable secrète ni requête cloud.
- README, VERSIONS, CONTEXT et AGENTS doivent être actualisés lors de chaque évolution.

## Connaissances sur les thermostats

- `workingMode`: 0 Auto, 1 Confort, 2 Confort -1, 3 Confort -2, 4 Éco, 5 Hors gel, 6 Off, 7 Vacances.
- Codes fil pilote pour capacité 6, `weeklyEvents.mm`, `holidays.mm`: 0 Off, 2 Confort, 3 Éco, 8 Hors gel, 9 Confort -1, 10 Confort -2.
- `comfortTemp` est la consigne Confort en °C. `weeklyEvents.t` correspond à la minute absolue depuis le début de la semaine, avec `d` indice 0..6 ; nom du jour `d=0` non encore confirmé.
- Mode Vacances : `workingMode=7`, `holidays.until` UTC et `holidays.mm` 3/8/0. L'annulation envoie `workingMode=0` sans champ `holidays` dans la **requête**, et un POST maison `isAtHome:true`. Supprimer effectivement le champ en base n'est pas confirmé.
- La propriété `loadShedding` ne doit **jamais** être écrite et ne prouve pas l'état actuel d'un effacement. Les valeurs kWh sont disponibles mais leur accumulation/période est inconnue.

## Inconnues / limites

- Contrôles de version, conflit ou champs requis du PUT thermostat, et comportement pendant un effacement actif : écriture reportée.
- Jour civil correspondant à `weeklyEvents.d=0`.
- Nature temporelle des valeurs kWh et signaux d'énergie.
- Déclenchement et fonctionnement du WebSocket.
- Quotas cloud réels et politique de polling optimale.
- HTTP 304 si le backend utilise un cache ETag : pas de cache implémenté.
- Persistance sécurisée côté HA, à concevoir selon les mécanismes natifs HA.

## Validation et prochaines étapes

- Suite automatique v0.2.0 : **51 tests réussis localement**, sans API de production.
- Contrôler sur GitHub la CI et le commit de la v0.2.0 après application du patch au dépôt personnel.
- Eventuellement publier sur PyPI après validation packaging et usages du SDK ; ne pas activer l'upload automatiquement.
- Créer ensuite `ha-vav-connect` : config flow, coordinator, entités en lecture seule, refresh et stockage de session confié à HA.
