# CONTEXT — vav-connect-api

## Architecture

SDK Python 3.11+ / `aiohttp`, asynchrone, indépendant de Home Assistant. Objectif futur : intégration HACS dans un **deuxième dépôt** `ha-vav-connect`. Python choisi pour utilisation directe dans HA sans serveur Node, choix détaillé dans README. Branche `ts/rest` reportée (non créée).

## Historique et validations réelles — 18/10/2026

- v0.1.x : authentification, lecture cloud de cinq zones, températures et capteurs.
- v0.2.0 : `POST /refreshToken` sans body, header `token` contenant le **refresh token** ; rotation des deux tokens et nouveau GET acceptés en conditions réelles ; robustesse, stockage configurable.
- Banc d'essai expérimental **séparé** : changement de mode individuel (Confort -2), modification ponctuelle et groupée d'horaires (lundi=0), Présence/Absence, Vacances/Hors gel, annulation, et modification de consigne Confort. Vérifications réelles GET et observations dans l'application officielle.
- Méthodes d'écriture observées : **PATCH** `/homes/{homeId}` pour `isAtHome`, **PUT** `/hubs/{hubId}/local-services/{serviceId}` pour le service thermostat complet. Les POST initiaux supposés pour ces routes étaient incorrects.
- Mode thermostat `workingMode` : 0 Auto,1 Confort,2 Confort -1,3 Confort -2,4 Éco,5 Hors gel,6 Off,7 Vacances. `holidays.mm` et `weeklyEvents.mm` : 0 Off,2 Confort,3 Éco,8 Hors gel,9 Confort -1,10 Confort -2. `d=0` lundi, `t=1440*d+minuteDuJour`.
- Otodo **peut conserver `holidays`** sur des thermostats revenus à `workingMode=0` Auto ; cela ne signifie pas que Vacances est actif.
- v0.3.0 : intégration des commandes dans le SDK, mais **lecture seule par défaut** et double opt-in `allow_writes=True` + `apply=True`. Précontrôle des données, refus si `loadShedding` non-false, contrôle juste avant PUT, GET de vérification, état partiel explicite. **83 tests locaux synthétiques** ; les nouvelles méthodes v0.3.0 n'ont PAS encore été appelées sur Otodo réel dans cet environnement.

## Risques et suites

- `loadShedding=false` ne prouve pas l'absence de délestage/effacement actif. Aucune écriture du champ, du Zigbee ou désappairage de passerelle. Vérifier indépendamment avec VAV avant commandes.
- Pas de transaction globale ni de contrôle atomique de version/ETag connu : conflit concurrent possible après la dernière relecture. Pas de rollback automatique ni retry PUT/PATCH.
- KWh cumulative/intervalle inconnu, quotas API inconnus, WebSocket non étudié, HTTP 304 sans cache.
- Première suite : tester les nouveaux aperçus sur compte réel, puis les écritures **sous supervision hors effacement** ; ensuite HACS avec config flow/Coordinator et pilotage opt-in.
