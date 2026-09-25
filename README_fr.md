# CommunityTrust Protocol — CTP Core v2.0

> *"Je suis parce que nous sommes"* — Philosophie Ubuntu, Afrique australe

[![DOI v0.1](https://zenodo.org/badge/DOI/10.5281/zenodo.20031237.svg)](https://doi.org/10.5281/zenodo.20031237)
[![Licence: CC BY-SA 4.0](https://img.shields.io/badge/Licence-CC%20BY--SA%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-sa/4.0/)
[![ORCID](https://img.shields.io/badge/ORCID-0009--0006--0220--3006-green.svg)](https://orcid.org/0009-0006-0220-3006)
[![Statut](https://img.shields.io/badge/Statut-v2.0%20pr%C3%A9publication%2C%20non%20relue-orange.svg)]()

**Auteur :** Ange AWALA  
**Organisation :** OpenScience Community  
**Contact :** [ange.awala.bj@gmail.com](mailto:ange.awala.bj@gmail.com) · [opensciencec@gmail.com](mailto:opensciencec@gmail.com)

[English version](README.md)

---

## Qu'est-ce que CTP ?

Les systèmes de confiance existants mesurent la **popularité**, la **richesse** ou le **statut institutionnel**. CTP mesure la **fiabilité comportementale dans le temps**.

Inspiré des tontines africaines — où la confiance collective remplace la garantie bancaire —, CTP est un mécanisme de réputation dans lequel une contribution ne compte qu'après approbation par un panel de **témoins tirés au sort qui engagent leur propre score**.

CTP est un **cadre paramétrable**, pas un moteur universel : les bons paramètres dépendent de la nature des contributions, de la précision des témoins et du coût d'une identité. Chaque application doit être calibrée et évaluée.

> **La v2.0 corrige des erreurs démontrables des versions v0.1 et v1.1** (condition anti-collusion, incitations manquantes, audit qui épargnait les coalitions, simulation incapable de tester la collusion…). Voir l'erratum de l'article (annexe A) et les tickets [#2 à #9](https://github.com/opensciencec/ctp/issues?q=label%3Aerratum).

---

## Le modèle (v2.0)

Chaque membre a un score τ ∈ [0,1] :

```
τ(t+1) = clip(τ + G + R − L − S − D − W, 0, 1)
```

| Terme | Signification |
|---|---|
| **G** = η · q(s) | gain de l'auteur d'une contribution acceptée et non sanctionnée |
| **R** = η_W / k | récompense du témoin qui vote avec l'issue (versée aux seuls membres actifs) |
| **L** = κ | défaut d'engagement |
| **S** = κ_s | sanction de l'auteur d'une contribution sanctionnée |
| **D** = δ · τ | dépréciation sans contribution acceptée |
| **W** = φ · τ | sanction de chaque témoin ayant approuvé un signal sanctionné ou piège |

S'y ajoutent : audit uniforme avec **contre-audit**, **panel adaptatif** (3 témoins au minimum) et **signaux pièges** contre la validation sans vérification.

**Paramètres recommandés (v2.1), dérivés de conditions fermées :**

| η | κ | η_W | κ_s | φ | p_a | k_min | θ | h | δ |
|---|---|---|---|---|---|---|---|---|---|
| 0,02 | 0,35 | 0,005 | 0,10 | 0,30 | 0,15 | 5 | 2/3 | 0,05 | 0,02 |

---

## Principaux résultats (simulation, jusqu'à 200 graines, IC 95 %)

| | Règles v1.1 | v2.1 |
|---|---|---|
| Défaut toléré | ≈ 1 période sur 4 | ≈ 1 période sur 20 |
| Score final des colludeurs (coalition de 30 %) | 0,58 (au-dessus du départ) | 0,06 |
| Fraudes acceptées | 2,5 % | 0,5 % |
| Agents adaptatifs : part qui fraude | 95 % (effondrement) | ≈ 7 % (niveau d'exploration) |

- L'audit seul laisse passer **85 %** des fraudes au même taux d'audit ; pour égaler le panel de témoins, il faudrait auditer environ 99 % des contributions.
- Sans responsabilité des témoins, les agents adaptatifs s'effondrent (92 % de fraude).
- **Condition d'applicabilité :** les témoins doivent bien juger. Pour les **tontines**, les paiements sont vérifiables : l'instanciation recommandée **n'utilise pas de témoins** (paiements vérifiés par l'opérateur, rotation par score, parrainage et exclusion).

**Limites :** pas encore de données de terrain ([#11](https://github.com/opensciencec/ctp/issues/11)), pas de relecture par les pairs ([#12](https://github.com/opensciencec/ctp/issues/12)).

---

## Structure du dépôt

```
ctp/
├── article-v2.0/          ← article de référence (FR + EN, PDF + LaTeX), figures, résultats
├── simulations-v2.0/      ← script qui produit chaque chiffre et figure de l'article
├── historique/            ← CTP Core v0.1 et v1.1 (obsolètes, conservées pour la traçabilité)
├── .github/               ← modèles de tickets et de PR, CI (compilation, reproductibilité)
├── CITATION.cff
└── CONTRIBUTING.md
```

---

## Démarrage rapide

```bash
git clone https://github.com/opensciencec/ctp.git && cd ctp
pip install -r simulations-v2.0/requirements.txt

python simulations-v2.0/ctp_core_v2_experiments.py figures   # retracer les figures (secondes)
python simulations-v2.0/ctp_core_v2_experiments.py E3        # recalculer une expérience
python simulations-v2.0/ctp_core_v2_experiments.py           # tout recalculer (~30 min, 8 cœurs)
```

Lire : [`article-v2.0/CTP_Core_v2.0_FR.pdf`](article-v2.0/CTP_Core_v2.0_FR.pdf) · [`article-v2.0/CTP_Core_v2.0_EN.pdf`](article-v2.0/CTP_Core_v2.0_EN.pdf)

---

## Principes éthiques

1. **Autonomie communautaire** — renforce l'auto-gouvernance sans dépendance institutionnelle
2. **Réciprocité** — le mécanisme est calibré pour rendre le parasitisme durable non rentable
3. **Mémoire courte réparable** — un défaut passé ne condamne pas à vie
4. **Transparence des règles, confidentialité des personnes** — les règles sont publiques, les scores non (sauf décision du Node)
5. **Non-marchandisation du score** — le score n'est ni un jeton, ni un actif, ni échangeable
6. **Décentralisation des données** — chaque Node gère ses propres données

---

## Citation

Voir [`CITATION.cff`](CITATION.cff). Version fondatrice :

```bibtex
@misc{awala2026ctp,
  author    = {Awala, Ange},
  title     = {{CommunityTrust Protocol (CTP v0.1)}},
  year      = {2026},
  doi       = {10.5281/zenodo.20031237},
  publisher = {Zenodo}
}
```

---

## Contribuer

Signalez une erreur avec le modèle de ticket **Erratum**, posez une question avec **Question**, ou ouvrez une pull request — voir [`CONTRIBUTING.md`](CONTRIBUTING.md). Chaque chiffre doit être reproductible ; une erreur publiée est corrigée **et** consignée dans l'erratum.

---

## Licence

[Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)](https://creativecommons.org/licenses/by-sa/4.0/)

Copyright © 2026 Ange AWALA — OpenScience Community

<div align="center">

*"Je suis parce que nous sommes"*

</div>
