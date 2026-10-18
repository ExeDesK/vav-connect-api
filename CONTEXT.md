# CONTEXT — vav-connect-api

## Objectif

Creer un SDK Python independant et asynchrone pour l'application Android VAV Connect/Otodo, puis une integration Home Assistant native HACS dans un **autre depot**. Conserver la passerelle VAV connectee et preservee pour l'effacement electrique.

## Decisions (18 octobre 2026)

- `main` : Python 3.11+, `aiohttp`, modeles dataclasses, PyPI ulterieurement. Justification expliquee dans `README.md`.
- `ts/rest` : branche experimentale envisageant TypeScript et Fastify, **sans etre une alternative supportee**. La variante mature pourra devenir un depot/paquet distinct.
- v0.1.x : lecture seule des donnees du logement, passerelles, pieces, equipements et thermostats ; aucun PUT, PATCH, DELETE ni commande Presence/Absence/Vacances.
- Controle de session : POST `/authenticate` et POST `/refreshToken` sans body, avec header `token`. Le token exact de refresh est **a confirmer** (supposition : refresh token).
- Les donnees utilisateurs reels ne figurent dans **aucun fichier** du depot. Jeux de test synthetiques uniquement.
- Toute evolution garde la compatibilite Python et une batterie de tests ; README, VERSIONS et CONTEXT doivent rester a jour.

## Points encore inconnus

- `token` du refresh : access ou refresh token ? Les valeurs de la capture etaient masquees.
- Semantique exacte de la capacite energie kWh et etats de signaux.
- `weeklyEvents.d=0` represente-t-il lundi ou dimanche ?
- GET post-annulation de Vacances : le serveur supprime-t-il effectivement la cle `holidays` ?
- Support d'un PUT partiel, controle de version/conflits, interactions avec l'effacement electrique.
- Quotas Otodo et frequence de lecture adaptee.
- Notifications via WebSocket, non implementees.
- Necessite d'adapter les headers `useragent`/`mobileversion` si l'application evolue.

## Avancement de la validation reelle (18 octobre 2026)

- `v0.1.0` : test reel des lectures `get_snapshot()` reussi sur compte autorise, avec associations des thermostats et temperatures coherentes. Aucun secret ni identifiant reel sauvegarde dans le depot.
- `v0.1.1` : script `examples/verify_refresh.py` pour valider manuellement le renouvellement explicite ; resultat reel en attente.

## Prochaines actions

1. Tester un refresh explicite (`--header-token refresh`), puis eventuellement la variante access si erreur ; ne pas divulguer de token.
2. Verifier l'utilisation du nouveau jeton par un GET apres renouvellement.
3. Publier la bibliotheque apres validation, puis creer `ha-vav-connect` dans son propre depot.
4. Experimenter `ts/rest` seulement si une API REST externe est reellement necessaire.
