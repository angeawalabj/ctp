# Contribuer à CTP

Merci de votre intérêt. Ce dépôt contient un travail de recherche : chaque
affirmation doit être démontrée ou mesurée, et chaque chiffre doit pouvoir être
reproduit.

## Signaler un problème

- **Erreur dans un article** (équation, preuve, chiffre) : modèle de ticket
  *Erratum*. Donnez la version, la section et un contre-exemple ou un calcul.
- **Question sur le modèle** : modèle de ticket *Question*.

## Proposer une modification

1. Forkez le dépôt et créez une branche depuis `main` :
   `recherche/…`, `simulation/…`, `docs/…` ou `ci/…`.
2. Messages de commit à l'impératif, préfixés : `recherche:`, `simulation:`,
   `docs:`, `ci:`, `chore:`.
3. Ouvrez une pull request vers `opensciencec/ctp:main` en remplissant le
   modèle, et liez les tickets (`Closes #…`).
4. La CI compile les articles et vérifie la reproductibilité des simulations ;
   les PDF et figures sont disponibles en **aperçu** dans les artefacts de
   l'exécution.

## Règles de reproductibilité

- Tout chiffre ou figure d'un article provient de
  `simulations-v2.0/ctp_core_v2_experiments.py` et de
  `article-v2.0/figures/resultats_v2.json`.
- Une modification du modèle impose de relancer les expériences concernées et
  de mettre à jour le texte.
- Une erreur découverte dans une version publiée est corrigée **et** consignée
  dans l'erratum (annexe A de l'article), jamais effacée silencieusement.
