# Consignes de contribution — vav-connect-api

1. **Préserver l'effacement électrique** : le SDK reste en lecture seule pour les équipements. Aucun désappairage de passerelle, aucune modification réseau/Zigbee ni écriture de `loadShedding`. Le POST est réservé à `/authenticate` et `/refreshToken`.
2. **Pas de données réelles dans Git** : jamais de mots de passe, access/refresh tokens, HAR, APK, adresses privées, clés Zigbee (`properties.keyList[].v`), secrets de passerelle (`aesKey`, `secretKey`, `wifiPwd`), informations de point de livraison électrique ou noms de personnes. Fixtures intégralement synthétiques.
3. Aucun test automatique ne contacte Otodo : chaque test HTTP utilise exclusivement le faux serveur sur `127.0.0.1`. Les vérifications manuelles sur compte autorisé sont hors CI.
4. Réutiliser les faits confirmés : `/refreshToken` reçoit **le refresh token** dans le header `token`, sans corps. En cas de succès, `access_token` ET `refresh_token` tournent. La persistance des deux doit être cohérente.
5. Distinguer strictement `WorkingMode` (`0..7`) des `PilotMode` (`0,2,3,8,9,10`). Ne pas assimiler `loadShedding=false` à une absence d'effacement en cours, ni la valeur kWh à un compteur cumulatif sans preuve.
6. Sécurité HTTP : ne pas suivre les redirections, ne jamais logger en-têtes secrets ni corps de réponses, différencier 401/403, ne pas réémettre de POST de refresh automatiquement après erreur/transient, ne pas relancer en boucle sur 429.
7. APIs publiques typées, asynchrones et indépendantes de Home Assistant. Exclure les secrets des dataclasses visibles et des erreurs. Les sauvegardes de tokens sont contrôlées par l'appelant, jamais effectuées automatiquement par le SDK.
8. Pour chaque changement : tests, README, VERSIONS et CONTEXT actualisés ; documenter le protocole dans `docs/PROTOCOL.md` si nécessaire.
9. Les futures écritures ne devront être envisagées qu'après validation de leur sûreté vis-à-vis de l'effacement, des conflits d'écriture et de la programmation. Aucun essai destructeur ou commande de chauffe en CI.
10. La branche expérimentale `ts/rest` a été **reportée par l'utilisateur**. Ne pas la créer sans nouvelle décision. Si les cycles de release divergent, privilégier des paquets/dépôts distincts.
