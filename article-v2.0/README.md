# Article CTP Core v2.0

- `CTP_Core_v2.0_FR.tex` / `.pdf` : article (français, 16 pages).
- `CTP_Core_v2.0_EN.tex` / `.pdf` : version anglaise, pour soumission.
- `figures/` : figures (`*_en.pdf` pour la version anglaise) et
  `resultats_v2.json`, produits par `../simulations-v2.0/ctp_core_v2_experiments.py`.

Reproduire :

```bash
python3 ../simulations-v2.0/ctp_core_v2_experiments.py            # tout (≈ 30 min, 8 cœurs)
python3 ../simulations-v2.0/ctp_core_v2_experiments.py figures    # retracer sans recalculer
latexmk -pdf CTP_Core_v2.0_FR.tex && latexmk -pdf CTP_Core_v2.0_EN.tex
```

Les corrections par rapport à v0.1/v1.1 sont listées dans l'annexe A
(erratum) de l'article.
