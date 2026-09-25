# CommunityTrust Protocol — CTP Core v2.0

> *"Je suis parce que nous sommes"* — Philosophie Ubuntu, Afrique australe
>
> *"I am because we are"*

[![DOI v0.1](https://zenodo.org/badge/DOI/10.5281/zenodo.20031237.svg)](https://doi.org/10.5281/zenodo.20031237)
[![License: CC BY-SA 4.0](https://img.shields.io/badge/License-CC%20BY--SA%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by-sa/4.0/)
[![ORCID](https://img.shields.io/badge/ORCID-0009--0006--0220--3006-green.svg)](https://orcid.org/0009-0006-0220-3006)
[![Status](https://img.shields.io/badge/Status-v2.0%20preprint%2C%20not%20peer%20reviewed-orange.svg)]()

**Author:** Ange AWALA  
**Organisation:** OpenScience Community  
**Contact:** [ange.awala.bj@gmail.com](mailto:ange.awala.bj@gmail.com) · [opensciencec@gmail.com](mailto:opensciencec@gmail.com)

[Version française](README_fr.md)

---

## What is CTP?

Existing trust systems measure **popularity**, **wealth**, or **institutional status**. CTP measures **behavioural reliability over time**.

Inspired by African tontines — where collective trust replaces bank guarantees — CTP is a reputation mechanism in which a contribution only counts after approval by a randomly drawn panel of **witnesses who stake their own score**.

CTP is a **parameterised framework**, not a universal engine: the right parameters depend on the nature of contributions, witness accuracy and the cost of an identity. Each application must be calibrated and evaluated.

> **v2.0 corrects demonstrable errors in v0.1 and v1.1** (anti-collusion condition, missing incentives, audit that spared coalitions, simulation unable to test collusion…). See the erratum in the article (Appendix A) and issues [#2–#9](https://github.com/opensciencec/ctp/issues?q=label%3Aerratum).

---

## The model (v2.0)

Each member has a score τ ∈ [0,1]:

```
τ(t+1) = clip(τ + G + R − L − S − D − W, 0, 1)
```

| Term | Meaning |
|---|---|
| **G** = η · q(s) | author's gain for an accepted, non-sanctioned contribution |
| **R** = η_W / k | witness reward for voting with the outcome (paid only to active members) |
| **L** = κ | commitment default |
| **S** = κ_s | sanction of the author of a sanctioned contribution |
| **D** = δ · τ | depreciation when no accepted contribution |
| **W** = φ · τ | sanction of each witness who approved a sanctioned or decoy signal |

Plus: uniform audit with **counter-audit**, **adaptive panel** (min. 3 witnesses), and **decoy signals** against rubber-stamping.

**Recommended parameters (v2.1), derived from closed-form conditions:**

| η | κ | η_W | κ_s | φ | p_a | k_min | θ | h | δ |
|---|---|---|---|---|---|---|---|---|---|
| 0.02 | 0.35 | 0.005 | 0.10 | 0.30 | 0.15 | 5 | 2/3 | 0.05 | 0.02 |

---

## Key results (simulation, up to 200 seeds, 95 % CI)

| | v1.1 rules | v2.1 |
|---|---|---|
| Default tolerated | ≈ 1 period in 4 | ≈ 1 period in 20 |
| Colluders' final score (30 % coalition) | 0.58 (above start) | 0.06 |
| Frauds accepted | 2.5 % | 0.5 % |
| Adaptive agents: share who cheat | 95 % (collapse) | ≈ 7 % (exploration level) |

- Audit alone lets **85 %** of frauds through at the same audit rate; matching the witness panel would require auditing ~99 % of contributions.
- Without witness accountability, adaptive agents collapse (92 % fraud).
- **Applicability condition:** witnesses must judge accurately. For **tontines**, payments are verifiable, so the recommended instantiation uses **no witnesses**: operator-verified payments, score-based rotation order, sponsorship and exclusion.

**Limits:** no field data yet ([#11](https://github.com/opensciencec/ctp/issues/11)), not peer reviewed ([#12](https://github.com/opensciencec/ctp/issues/12)).

---

## Repository structure

```
ctp/
├── article-v2.0/          ← reference article (FR + EN, PDF + LaTeX), figures, results
├── simulations-v2.0/      ← script producing every number and figure of the article
├── historique/            ← CTP Core v0.1 and v1.1 (obsolete, kept for traceability)
├── .github/               ← issue/PR templates, CI (article build, reproducibility check)
├── CITATION.cff
└── CONTRIBUTING.md
```

---

## Quick start

```bash
git clone https://github.com/opensciencec/ctp.git && cd ctp
pip install -r simulations-v2.0/requirements.txt

python simulations-v2.0/ctp_core_v2_experiments.py figures   # redraw all figures (seconds)
python simulations-v2.0/ctp_core_v2_experiments.py E3        # recompute one experiment
python simulations-v2.0/ctp_core_v2_experiments.py           # recompute everything (~30 min, 8 cores)
```

Read: [`article-v2.0/CTP_Core_v2.0_EN.pdf`](article-v2.0/CTP_Core_v2.0_EN.pdf) · [`article-v2.0/CTP_Core_v2.0_FR.pdf`](article-v2.0/CTP_Core_v2.0_FR.pdf)

---

## Ethical principles

1. **Community autonomy** — strengthens self-governance without institutional dependency
2. **Reciprocity** — the mechanism is calibrated to make long-term free riding unprofitable
3. **Repairable short memory** — a past default does not condemn for life
4. **Rule transparency, personal confidentiality** — rules are public, scores are not (unless the Node decides otherwise)
5. **Non-commodification of score** — the score is not a token, not an asset, not tradeable
6. **Data decentralisation** — each Node manages its own data

---

## Citing this work

See [`CITATION.cff`](CITATION.cff). Founding version:

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

## Contributing

Report an error with the **Erratum** issue template, ask with **Question**, or open a pull request — see [`CONTRIBUTING.md`](CONTRIBUTING.md). Every number must be reproducible; published errors are corrected **and** recorded in the erratum.

---

## License

[Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)](https://creativecommons.org/licenses/by-sa/4.0/)

Copyright © 2026 Ange AWALA — OpenScience Community

<div align="center">

*"I am because we are"*

</div>
