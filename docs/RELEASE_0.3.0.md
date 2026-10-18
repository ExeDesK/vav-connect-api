# v0.3.0 — Commands opt-in (alpha)

- SDK Python toujours **lecture seule par défaut**. Deux accords indépendants pour écrire : `allow_writes=True` et `apply=True`.
- Contrôle individuel : mode Confort/Éco/Hors-gel/Arrêt, température Confort, programmation complète ou jours choisis.
- Contrôle global : Présence/Absence (`PATCH /homes/{id}` et `PUT` thermostats), Vacances (`PUT` sans PATCH maison), annulation anticipée.
- Prévisualisation de chaque transition horaire, précontrôle des données, relecture avant écriture, vérification après, aucune relance automatique PUT/PATCH.
- Prise en charge du cas réel : `holidays` historique peut persister après retour Auto ; reprise des annulations globales partiellement effectuées.
- **83 tests locaux synthétiques** ; protocoles d'écriture vérifiés séparément sur VAV réel, mais les nouvelles méthodes v0.3.0 du SDK ne sont pas encore validées directement sur la production.
- Documentation et protocole actualisés.

**Prudence :** absence de garanties de cohérence atomique ou de compatibilité pendant un effacement électrique actif. La passerelle VAV reste pleinement gérée par VAV ; l'utilisateur doit vérifier les événements réseau avant chaque écriture.
