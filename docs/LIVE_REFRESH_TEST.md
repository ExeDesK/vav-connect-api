# Valider le renouvellement du token Otodo sur un compte autorise

Le SDK est en lecture seule. **Ce test appelle uniquement** :

1. `POST /authenticate` (connexion)
2. `GET /homes` (verification avant)
3. `POST /refreshToken` avec body vide et header `token` (renouvellement explicite)
4. `GET /homes` (verification apres)

Aucun `PUT`, aucune commande de radiateur, et aucune modification d'effacement electrique. L'appel de refresh peut toutefois faire tourner les tokens de session et, selon les regles de session Otodo encore inconnues, obliger un appareil deja connecte a se reconnecter.

## Sur Windows PowerShell

Se placer dans le repertoire `vav-connect-api` avec `.venv` deja active :

```powershell
$env:VAV_EMAIL = Read-Host "Email VAV"
$env:VAV_PASSWORD = [System.Net.NetworkCredential]::new("", (Read-Host "Mot de passe VAV" -AsSecureString)).Password
try {
    python .\examples\verify_refresh.py --header-token refresh
} finally {
    Remove-Item Env:\VAV_PASSWORD -ErrorAction SilentlyContinue
}
```

Ne jamais ecrire de jeton ou de mot de passe dans les fichiers, le chat, le terminal en clair, ni dans Git.

## Resultats possibles

- **Etapes 1/4 a 4/4 OK** : le serveur accepte le header `token` avec le **refresh token** ; la session retournee fonctionne pour un GET.
- **Echec a l'etape 3/4, HTTP 401/403** : le serveur refuse l'hypothese `refresh`. L'hypothèse refresh est pourtant confirmée par le test réel du 18/10/2026 : relever la réponse du serveur et vérifier une éventuelle évolution de l'API, sans relancer en boucle.
- **Echec a l'etape 4/4** : le serveur a repondu au refresh mais le nouveau token ne fonctionne pas pour une lecture. Ne pas considerer le refresh valide.
- **HTTP 429** : quota atteint ; stopper les essais.
- **TransportError/ProtocolError** : verifier la connexion ou comparer au trafic HTTP Toolkit sans divulguer de secrets.

Pour tester la seconde hypothese, remplacer `refresh` par `access` dans la commande. Chaque execution du script ne fait **qu'un seul** appel `/refreshToken` et **aucune reconnexion automatique** apres un echec.

Le script n'affiche que des etats OK/echec et indique si les nouvelles valeurs d'access et de refresh ont change ; il n'affiche ni tokens ni identifiants du logement.

**Important** : ce test confirme que le serveur accepte le refresh token ; il ne prouve pas que tous les clients Android utilisent exactement ce mécanisme dans toutes les situations.

## Résultat réel confirmé — 18 octobre 2026

L'essai manuel `--header-token refresh` a **réussi** sur un compte autorisé :

- Authentification `POST /authenticate` : OK.
- `GET /homes` avec l'ancien access token : OK.
- `POST /refreshToken` sans body et avec **refresh token** dans l'en-tête `token` : OK.
- Nouvelle paire reçue, **access et refresh tous deux différents** des anciens.
- `GET /homes` avec le nouvel access token : OK.

Aucune valeur de jeton n'a été enregistrée dans le dépôt. La variante `--header-token access` n'est donc **plus nécessaire** pour implémenter la session. Le diagnostic historique conserve cette option uniquement pour compatibilité v0.1.x.

Ce test confirme les endpoints de session et leur rotation, mais ne constitue pas encore une validation d'une exécution continue après 30 jours ni d'un stockage persistant Home Assistant.
