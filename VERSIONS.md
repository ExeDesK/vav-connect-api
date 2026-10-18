# Historique des versions

## 0.1.1 — 2026-10-18 — diagnostic du refresh

- Exemple manuel `examples/verify_refresh.py` : teste login, lecture, refresh explicite et lecture apres refresh sur un compte autorise.
- Deux possibilites testables individuellement (`--header-token refresh` ou `access`), sans retry silencieux ni divulgation de jetons.
- Six tests supplementaires sur faux serveur local : succes, refus 401 sans reconnexion, variante access et absence d'identifiants.
- Documentation de verification dans `docs/LIVE_REFRESH_TEST.md`.
- Confirmation de la compatibilite reelle des **lectures** du SDK v0.1.0. Refresh de production encore a confirmer.


## 0.1.0 — 2026-10-18 — alpha SDK Python, lecture seule

- Nouveau depot `vav-connect-api`, independant de l'integration HACS.
- Client `aiohttp` avec login Otodo (`POST /authenticate`), header `token`, refresh sans body (`POST /refreshToken`) et re-authentification limitee en cas de 401.
- Support du renouvellement preventif avec marge de 300 secondes et partage de session entre requetes concurrentes.
- Endpoints GET : logement, passerelles, pieces, appareils, thermostats par passerelle et snapshot associe.
- Modeles immuables de lecture : modes 0–7, ordres fil pilote, vacances, horaires, capteurs, puissance et valeur kWh non qualifiee.
- Filtrage explicite des champs sensibles (cles Zigbee, Wi-Fi, secrets cloud/metadonnees de logement).
- Tests automatiques sans appel au cloud Otodo.
- README : justification du choix Python plutot que TypeScript et objectif de la branche experimentale `ts/rest`.
- Limites explicites : absence de pilotage, identification du jeton de refresh non confirmee, aucune validation sur un compte reel a ce stade.
