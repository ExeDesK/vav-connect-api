# v0.2.0 — Fiabilité du SDK VAV Connect (lecture seule)

## Changements

- Renouvellement du refresh token **validé sur l'API Otodo réelle** avec rotation des deux jetons.
- Sauvegarde/restauration explicites d'une session (`SessionTokens.to_storage()` et `from_storage()`) ; aucune sauvegarde ou protection des secrets implicite.
- Retry conservateur des GET sur erreurs réseau ou HTTP transitoires, sans relance d'écritures de session ni de requêtes soumises au quota.
- Distinction 401/403, `Retry-After` sur 429 et redirections interdites pour protéger le header `token`.
- Propriétés de lecture enrichies pour modules, capteurs, thermostats et programmations.
- GET `/health` du cloud et CI GitHub Actions Python 3.11 à 3.13.
- **51 tests locaux réussis**, aucune commande de chauffage ni modification de l'effacement électrique.

## Limites

Alpha communautaire non officielle, toujours **lecture seule**. Aucun contrôle des thermostats ni de présence/absence/vacances. Valeur énergie kWh et `loadShedding` non interprétées comme état d'effacement. Aucune publication PyPI automatique.

## Vérifications

```powershell
python -m pip install -e ".[dev]"
python -m pytest -q
python -m build --sdist --wheel
```
