# Politique de robustesse, session et confidentialité — v0.2.0

## Authentification confirmée

Le client conserve les valeurs `access_token`, `refresh_token`, `expires_at` en mémoire et utilise le header propriétaire `token` pour les lectures.

- `POST /authenticate` : JSON `email`, `password`, `parkName: "vav"` ; reçoit les deux tokens et `expires_in`.
- `POST /refreshToken` : **body vide** (`Content-Length: 0`), header `token: <refresh_token>` ; **validé réellement** le 18/10/2026.
- À chaque refresh réussi, Otodo retourne une nouvelle paire d'access/refresh tokens ; les **deux** ont changé dans le test réel et le nouvel access token a permis un `GET /homes`.
- Le client renouvelle préventivement à moins de 5 minutes de l'expiration, et peut tenter un refresh après un premier HTTP 401. Un deuxième 401 est remonté sans nouvelle boucle de refresh.
- Un `asyncio.Lock` empêche deux rafraîchissements simultanés au sein d'une même instance `VAVClient`. **Deux processus distincts n'ont pas ce verrou en commun** : ne pas leur faire partager une même paire de refresh tokens sans coordination externe.

## Sauvegarde de session

`SessionTokens.to_storage()` renvoie un dictionnaire **avec les tokens en clair** (`schema_version:1`). `SessionTokens.from_storage()` vérifie la version, le type et la date d'expiration (avec fuseau). Le SDK n'écrit aucun fichier et ne chiffre pas les tokens.

Pour une application hôte :

1. Prévoir un stockage confidentiel aux permissions contrôlées.
2. Fournir un `token_callback` async qui persiste **la paire complète** à chaque connexion et renouvellement ; remplacer atomiquement l'ancien enregistrement.
3. Au redémarrage, charger avec `SessionTokens.from_storage()` puis construire `VAVClient(tokens=...)` ; facultativement transmettre des identifiants pour le fallback de connexion.
4. Ne jamais journaliser le retour de `to_storage()`, ni coller ce dictionnaire dans Git, les tickets ou les rapports d'erreurs.

Si `token_callback` échoue, le SDK **garde les nouveaux jetons en mémoire** et lève `TokenPersistenceError` sans afficher l'erreur originale du stockage, qui pourrait contenir des secrets. L'hôte doit corriger la persistance ou se réauthentifier après redémarrage.

> La sécurité du stockage Home Assistant reste à concevoir dans `ha-vav-connect`. Les config entries ou fichiers HA ne doivent **pas** être présentés comme chiffrés par défaut.

## Politique HTTP

| Situation | Comportement |
|---|---|
| HTTP 401 | Une reprise après renouvellement de session, au maximum. |
| HTTP 403 | `ForbiddenError`, sans refresh ni nouvelle authentification. |
| HTTP 429 | `RateLimitError`, **aucune** relance ; `retry_after_seconds` exposé si interprétable. |
| GET HTTP 408/500/502/503/504 | Jusqu'à `max_read_retries` nouvelles tentatives (1 par défaut), avec temporisation bornée. |
| GET erreur réseau / timeout | Même limite de retry GET ; `TransportError` à épuisement. |
| POST `/authenticate` ou `/refreshToken` | **Jamais** relancé automatiquement sur 5xx ou coupure ; un refresh peut avoir déjà tourné côté serveur. |
| HTTP 3xx, dont 304 | `ProtocolError`, sans suivre les redirections (protection contre la fuite du header `token`). Pas de cache ETag. |
| JSON inattendu | `ProtocolError`, sans imprimer le corps brut. |

Le SDK accepte `max_read_retries=0..3` et `retry_backoff_seconds=0..10` ; seule une lecture GET est concernée. `RateLimitError.retry_after` contient la valeur brute du header HTTP fourni par le serveur ; ne pas la logger si une politique stricte s'applique.

Les délais, quotas et règles de disponibilité d'Otodo ne sont pas documentés ; cette stratégie reste conservatrice et devra être adaptée aux observations en usage réel.

## Données exclues des modèles

Les projections de `/devices`, `/hubs` et `/homes` ne retiennent pas les champs arbitraires ou sensibles : clés Zigbee, copies de propriétés, secrets du hub, Wi-Fi, PDL, noms et coordonnées de l'installateur. Les tests introduisent volontairement des valeurs « secret » synthétiques pour prouver qu'elles n'atteignent pas la représentation des modèles ou les messages d'erreur.
