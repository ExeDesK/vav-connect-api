# Consignes de contribution — vav-connect-api

1. **Ne jamais affecter les fonctions d'effacement** : aucun desacouplage de passerelle, reconfiguration reseau/Zigbee, ou modification de `loadShedding`. Rester lecture seule jusqu'a des tests de securite documentes et une decision explicite.
2. Ne jamais commiter de tokens, mots de passe, HAR, APK, captures brutes ou cle Zigbee. Les tests et docs doivent utiliser uniquement des fixtures entierement **synthetiques** ; `properties.keyList[].v`, `temp[].properties`, `aesKey`, `secretKey`, `wifiPwd`, PDL et autres identifiants personnels sont sensibles.
3. Tous les appels HTTP dans les tests doivent cibler un serveur local simule ; aucun test automatique ne doit contacter le cloud reel. Les tests de compatibilite sur compte personnel sont manuels et volontaires.
4. Respecter les captures : le champ `token` est confirme, mais sa nature pour `/refreshToken` reste inconnue. Ne pas transformer une hypothese en fait.
5. Distinguer `WorkingMode` des ordres fil pilote (`PilotMode`). Ne pas assimiler `loadShedding` a un effacement actif, ni la valeur energie kWh a un compteur total sans preuve.
6. Garder les APIs publiques typees et asynchrones ; propager les erreurs explicites sans journaliser la charge utile ni les credentials.
7. Toute nouvelle fonctionnalite doit ajouter des tests, et mettre a jour `README.md`, `VERSIONS.md`, `CONTEXT.md` et `docs/PROTOCOL.md` quand le protocole change.
8. Les nouvelles ecritures (quand elles seront autorisees) devront obtenir un etat recemment relu, etre strictement limitees a l'intention de l'utilisateur, respecter les contraintes d'effacement et avoir des tests de conflit/idempotence. Aucun script de test ne doit envoyer de commande de chauffe a une installation de production.
9. La branche `ts/rest` est experimentale. Le SDK Python `main` ne depend d'aucun package Node. Quand les cycles de publication divergent, privilegier deux depots ou un monorepo a packages distincts, plutot que deux branches maintenues independamment.
10. Le script de diagnostic live du refresh ne doit jamais faire partie des tests CI : son execution est manuelle, avec identifiants d'un compte autorise, et la sortie ne contient aucun token.
