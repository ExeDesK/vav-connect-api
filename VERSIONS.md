# Historique des versions

## 0.3.0 — 2026-10-18 — commandes optionnelles

- Double opt-in `allow_writes=True` et `apply=True` ; aperçu des changements sans écriture par défaut.
- Modes, confort, calendrier complet ou par jour, Présence/Absence, Vacances et annulation anticipée.
- PUT du thermostat complet après contrôle de fraîcheur, sauvegarde des autres champs, `loadShedding` jamais modifié ; PATCH maison.
- Aucun retry des commandes ; vérification GET, exception d'état incertain et gestion des scénarios globaux partiels.
- Support des métadonnées `holidays` persistantes alors que le mode est Auto ; `d=0` correspond au lundi.
- Documentation CONTROL et exemple d'aperçu ; **83 tests locaux sur serveur simulé**. Le banc d'essai historique, distinct du SDK, a validé les routes sur VAV réel.

## 0.2.0 — 2026-10-18 — fiabilité et persistance de session

- Le refresh a été **validé sur le cloud réel Otodo** : `POST /refreshToken` avec le **refresh token** dans l'en-tête `token`, requête sans body, et rotation effective des **deux** jetons. Une lecture GET avec le nouvel access token a réussi.
- `SessionTokens.to_storage()` / `from_storage()` : format explicite versionné pour restaurer une session après redémarrage. Aucun stockage disque automatique et aucune garantie de chiffrement : l'appelant est responsable de la protection des secrets.
- Callback de tokens sérialisé et gestion de l'échec d'enregistrement avec `TokenPersistenceError` ; les nouveaux jetons restent actifs en mémoire en cas d'échec du callback.
- Conservation des identifiants de contexte si la réponse de refresh omet `homeId`, `parkId` ou `userId`.
- GET : retry borné et configurable sur erreur de transport ou HTTP `408/500/502/503/504` ; aucune relance de requête d'authentification, d'un HTTP 429 ou d'un accès interdit.
- HTTP 401 et 403 distingués ; `ForbiddenError` explicite. `RateLimitError.retry_after_seconds` interprète `Retry-After` si disponible.
- Protection contre les redirections HTTP : le header propriétaire `token` n'est pas retransmis à un serveur tiers. HTTP 304 reste un échec explicite tant que le cache n'est pas géré.
- Modèles enrichis : accès directs aux capteurs par zone, état d'alimentation du module, puissance nominale du radiateur, sélection des événements hebdomadaires par jour, filtrage des événements malformés.
- Nouveau GET `/health` pour la disponibilité **du cloud** exclusivement.
- CI GitHub Actions (3 versions de Python, tests hors ligne, construction des distributions) ; **51 tests locaux réussis** sur serveur simulé.
- README : justification Python vs TypeScript conservée ; branche `ts/rest` explicitement reportée.
- Toujours **strictement lecture seule** pour les équipements : aucune commande de radiateur ou d'effacement.

## 0.1.1 — 2026-10-18 — diagnostic du refresh

- Exemple `examples/verify_refresh.py` : connexion, lecture, renouvellement explicite, lecture avec le nouveau jeton, sans secrets affichés et sans reconnexion de secours masquant le résultat.
- Deux hypothèses de jetons testables indépendamment à l'époque (`refresh` ou `access`). Le test **réel ultérieur a confirmé `refresh`**.
- Tests supplémentaires sur un faux serveur local et documentation dans `docs/LIVE_REFRESH_TEST.md`.
- Premier `get_snapshot()` validé avec succès sur une installation VAV autorisée : logement, passerelle et cinq zones.

## 0.1.0 — 2026-10-18 — alpha SDK Python, lecture seule

- Client asynchrone `aiohttp` avec authentification `/authenticate`, header `token` et lecture des ressources cloud Otodo.
- Lecture `/homes`, `/hubs`, `/rooms`, `/devices`, `/hubs/{hubId}/local-services` ; association entre capteurs, modules et thermostats.
- Modèles immuables pour modes 0–7, ordres fil pilote, vacances et événements hebdomadaires.
- Filtrage des secrets Zigbee, Wi-Fi, des identifiants personnels non nécessaires.
- Tests sans accès au cloud, README expliquant le choix Python et architecture HACS séparée.
