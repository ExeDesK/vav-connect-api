# Otodo / VAV 4.14.4 — protocole observe au 18/10/2026

Ce document decrit exclusivement les **captures partagees**, sans replay de commandes vers le cloud. Les vrais identifiants, noms, adresse et secrets des captures ne sont pas inclus.

## Points HTTP observes

| Methode | Route | Objet | Dans SDK v0.1 |
|---|---|---|---|
| POST | `/authenticate` | Connexion `email`, `password`, `parkName: vav` | Oui |
| POST | `/refreshToken` | Renouvellement (aucun body, header `token`) | Oui, type du token non confirme |
| GET | `/homes` | Objet logement unique avec `isAtHome` | Oui |
| GET | `/hubs` | Liste des passerelles, contient aussi des **secrets** a filtrer | Oui, projection sure |
| GET | `/rooms` | Pieces | Oui |
| GET | `/devices` | Capteurs et modules, peut contenir des **cles Zigbee** | Oui, projection sure |
| GET | `/hubs/{hubId}/local-services` | Thermostats | Oui |
| GET | `/consumptions/signals` | Signaux de couleur/alertes | Non, semantique inconnue |
| PUT | `/hubs/{hubId}/local-services/{serviceId}` | Maj objet thermostat | Non (lecture seule) |
| POST | `/homes/{homeId}` | Presence/absence via `isAtHome` | Non (lecture seule) |

La methode PUT du thermostat est confirmee par les en-tetes de la capture du 18/10. Les mentions de POST thermostat dans les premieres notes etaient incorrectes.

## Headers Android 4.14.4

```http
Content-Type: application/json
language: fr
mobileversion: 4.14.4
timezoneid: GMT
token: <jeton>
useragent: android.vav.4.14.4
User-Agent: okhttp/4.12.0
```

`token` est un en-tete HTTP specifique, **non** `Authorization: Bearer ...` pour la capture de PUT. La reponse d'auth contient pourtant `token_type: Bearer`. Le SDK utilise `token` sur les GET, a confirmer par un test reel (la capture PUT demontre ce header).

La requete `POST /refreshToken` est **sans body** (Content-Length: 0). La reponse fournit `access_token`, `refresh_token`, `expires_in: 2592000` (secondes) et les identifiants de session. **On ne connait pas avec certitude lequel des deux tokens etait dans le header masque du refresh**. Le SDK suppose `refresh_token`; ce comportement est configurable, et doit etre valide par un essai reel.

## Proprietes du thermostat

- `_id` : identifiant du service thermostat ; `hubId`, `roomId` : liens vers les autres ressources.
- `workingMode` : mode global (`0` Auto, `1` Confort, `2` Confort -1, `3` Confort -2, `4` Eco, `5` Hors gel, `6` Off, `7` Vacances).
- `comfortTemp` : consigne Confort, en degres Celsius ; une modification 19 → 20 ne change pas le mode Auto ni les evenements hebdomadaires.
- `weeklyEvents` : evenements `{d, t, mm}` avec `t` correspondant a la minute absolue dans la semaine. Le premier jour civil `d=0` n'est pas encore determine.
- `holidays`: `{until: ISO_UTC, mm: code_fil_pilote}` en mode vacances `workingMode=7`. Valeurs observees : Eco = 3, Hors gel = 8, Off = 0.
- Annulation manuelle des vacances : POST maison `isAtHome: true`, PUT thermostat `workingMode: 0` sans propriete `holidays` **dans le body** ; suppression cote serveur non verifiee.
- Passage en Absence : POST maison `isAtHome:false`, PUT thermostats `workingMode:4` (Eco). Retour presence : `isAtHome:true`, `workingMode:0` (Auto).
- `loadShedding`: booleen recu, mais ne prouve ni l'activation d'un contrat d'effacement, ni l'existence d'un effacement en cours. **Aucune ecriture dans ce champ.**

## Modes fil pilote et caracteristiques d'equipement

| Capability ID | Mesure/commande | Lecture |
|---:|---|---|
| 4 | Temperature capteur | Kelvin x10, conversion `K/10 - 273.15` °C |
| 15 | Humidite | % |
| 20 | Batterie | % |
| 31 | Connectivite | 0 inatteignable, 1 atteignable |
| 6 | Code de mode module | 0/2/3/8/9/10 selon l'ordre fil pilote |
| 23 | Puissance | W |
| 18 | Energie | kWh, type de relevé (instantane/cumul) a confirmer |

La capacite 6 du module ne doit pas etre confondue avec `workingMode` du thermostat. De meme, la puissance electrique a 0 W ne prouve pas que le chauffage est dans un mode Off.

## Menaces et garde-fous

1. Les fichiers bruts `/devices` peuvent contenir des cles Zigbee dans `properties.keyList[].v` et des copies dans `temp[].properties` ; `/hubs` peut contenir des secrets de passerelle et Wi-Fi ; `/homes` peut contenir un identifiant de point de livraison et des renseignements personnels. **Ne jamais publier ces reponses brutes.**
2. Le SDK ne retourne que des champs choisis explicitement ; il ignore volontairement les `properties` et champs arbitraires. Les tests utilisent des donnees **synthetiques**.
3. Une ecriture de thermostat partielle n'est **pas encore validee**. Ne pas supposer qu'un PUT partiel fonctionne ni envoyer un PUT contenant un vieux `loadShedding`.
4. Aucun mecanisme documente de concurrence (`ETag`/version serveur) n'a ete identifie pour les modifications ; prudence avant toute commande.
5. La passerelle et le service d'effacement du reseau doivent continuer a fonctionner meme si le SDK ou Home Assistant est indisponible.
