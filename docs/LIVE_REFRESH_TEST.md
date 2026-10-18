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
- **Echec a l'etape 3/4, HTTP 401/403** : le serveur refuse l'hypothese `refresh`. Il peut utiliser l'**access token**, ou une autre logique. Ne pas relancer en boucle ; re-tester une seule fois avec `--header-token access`, en fournissant a nouveau le mot de passe via PowerShell.
- **Echec a l'etape 4/4** : le serveur a repondu au refresh mais le nouveau token ne fonctionne pas pour une lecture. Ne pas considerer le refresh valide.
- **HTTP 429** : quota atteint ; stopper les essais.
- **TransportError/ProtocolError** : verifier la connexion ou comparer au trafic HTTP Toolkit sans divulguer de secrets.

Pour tester la seconde hypothese, remplacer `refresh` par `access` dans la commande. Chaque execution du script ne fait **qu'un seul** appel `/refreshToken` et **aucune reconnexion automatique** apres un echec.

Le script n'affiche que des etats OK/echec et indique si les nouvelles valeurs d'access et de refresh ont change ; il n'affiche ni tokens ni identifiants du logement.

**Important** : accepter l'une des deux hypotheses prouve ce que le serveur autorise pour ce test, pas forcement la valeur envoyee par l'application Android elle-meme. Cette derniere identification demanderait une capture locale non masquee, comparee sans divulguer les valeurs.
