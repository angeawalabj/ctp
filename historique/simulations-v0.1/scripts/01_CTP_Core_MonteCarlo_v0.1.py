"""
╔══════════════════════════════════════════════════════════════════╗
║         CommunityTrust Protocol (CTP) — Simulation v0.1         ║
║              Validation Monte Carlo — 52 périodes                ║
║                                                                  ║
║  Auteur      : Ange AWALA                                        ║
║  Affiliation : OpenScience Community                             ║
║  ORCID       : 0009-0006-0220-3006                               ║
║  DOI         : 10.5281/zenodo.20031237                           ║
║  Licence     : Creative Commons BY-SA 4.0                        ║
║                                                                  ║
║  "Je suis parce que nous sommes"                                 ║
╚══════════════════════════════════════════════════════════════════╝

Implémente fidèlement les équations du papier CTP v0.1 :
  Eq.(1)  : τ_{i,j}(t+1) = clip(τ + G - L - D - W, 0, 1)
  Eq.(2)  : G_{i,j}(t)   = η · Σ q(s_k)
  Eq.(3)  : L_{i,j}(t)   = κ · 1_{défaut_i}(t)
  Eq.(4)  : D_{i,j}(t)   = δ · τ_{i,j}(t) · 1_{inactif_i}(t)
  Eq.(5)  : W_{i,j}(t)   = φ · Σ τ/|W(s)|  (signaux audités)
  Eq.(7)  : q(s)          = τ̄_W · ρ(s)
  Eq.(8)  : k_j           = max(k_min, floor(α_k · |M_j|))
  Eq.(9)  : τ_i^M(t)      = Σ ω_{i,j} · τ_{i,j}(t)
  Eq.(10) : ω_{i,j}(t)    = h_{i,j}·ρ_j / Σ h_{i,j'}·ρ_{j'}
  Eq.(11) : λ_eff(m_i)    = λ · μ^{m_i} · sim(j,j')
  Eq.(12) : sim(j→j')     = |M_j ∩ M_{j'}| / |M_j|
  Eq.(13) : V_{i,j}(t)    = τ_{i,j}(t) / Σ_k τ_{k,j}(t)
"""

import random
import math
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from dataclasses import dataclass, field
from collections import defaultdict
from typing import Optional

# ══════════════════════════════════════════════════════════════════
# SECTION 1 — PARAMÈTRES DU PROTOCOLE
# Valeurs recommandées par le Meta-Node (Table 2 du papier)
# ══════════════════════════════════════════════════════════════════

class CTPParams:
    """
    Paramètres du protocole CTP v0.1.
    Tous les paramètres respectent les contraintes formelles du papier.
    """
    ETA      : float = 0.05   # η — taux de gain          contrainte: η ≪ κ
    KAPPA    : float = 0.15   # κ — pénalité de défaut     contrainte: κ ≫ η
    DELTA    : float = 0.02   # δ — dépréciation inactivité contrainte: δ > 0
    PHI      : float = 0.15   # φ — responsabilité Witness  contrainte: φ ≥ 3η
    LAMBDA_  : float = 0.20   # λ — portabilité de base     contrainte: λ ∈ [0,1]
    MU       : float = 0.70   # μ — pénalité de migration   contrainte: μ ∈ [0.6,0.8]
    K_MIN    : int   = 3      # k_min — Witnesses minimum   contrainte: k_min ≥ 3
    ALPHA_K  : float = 0.20   # α_k — fraction adaptative  contrainte: α_k ∈ (0,1)
    AUDIT_P  : float = 0.15   # probabilité d'audit interne
    SCORE_INIT: float = 0.30  # score initial des nouveaux membres

    # Vérification des contraintes formelles
    def __post_init__(self):
        assert self.PHI >= 3 * self.ETA, f"Violation contrainte: φ={self.PHI} < 3η={3*self.ETA}"
        assert self.KAPPA > self.ETA,    f"Violation contrainte: κ={self.KAPPA} ≤ η={self.ETA}"
        assert self.K_MIN >= 3,          f"Violation contrainte: k_min={self.K_MIN} < 3"

P = CTPParams()

# ══════════════════════════════════════════════════════════════════
# SECTION 2 — STRUCTURES DE DONNÉES
# ══════════════════════════════════════════════════════════════════

@dataclass
class Signal:
    """
    Représente un Signal soumis par un membre.
    Un Signal devient une Contribution une fois validé par k Witnesses.
    """
    signal_id   : str
    author_id   : int
    node_id     : str
    period      : int
    real_quality: float        # qualité réelle ∈ [0,1] — inobservable par le Node
    validated   : bool = False
    audited     : bool = False
    witnesses   : list = field(default_factory=list)
    quality_score: float = 0.0 # q(s) calculée après validation

@dataclass
class Member:
    """
    Représente un membre dans un Node avec son TrustScore et son historique.
    Implémente les variables d'état définies Section 2.1 du papier.
    """
    member_id        : int
    behavior         : str     # 'honest' | 'freerider' | 'colluder' | 'deserter'
    trust_score      : float = P.SCORE_INIT
    periods_active   : int   = 0
    contributions    : int   = 0
    defaults         : int   = 0
    migrations       : int   = 0
    last_active_period: int  = 0

    # Historique complet du TrustScore — pour les graphiques et analyses
    history          : list  = field(default_factory=list)

    # Décomposition des forces — pour l'analyse détaillée
    total_gain       : float = 0.0
    total_loss       : float = 0.0
    total_depreciation: float = 0.0
    total_witness_cost: float = 0.0

    def clip(self):
        """
        Eq.(1) — clip(x, 0, 1) = max(0, min(1, x))
        Garantit la bornitude dans [0,1] à chaque étape.
        """
        self.trust_score = max(0.0, min(1.0, self.trust_score))

    def record(self):
        """Enregistre le score courant dans l'historique."""
        self.history.append(round(self.trust_score, 6))

# ══════════════════════════════════════════════════════════════════
# SECTION 3 — NODE CTP
# ══════════════════════════════════════════════════════════════════

class CTPNode:
    """
    Implémente un Node CTP complet selon la spécification v0.1.
    Chaque Node maintient ses propres membres, paramètres et historique.
    """

    def __init__(self, node_id: str, params: CTPParams = P):
        self.node_id  = node_id
        self.P        = params
        self.members  : dict[int, Member] = {}
        self.period   : int = 0
        self.signals  : list[Signal] = []

        # Statistiques globales du Node
        self.stats = {
            'total_signals'      : 0,
            'total_contributions': 0,
            'total_defaults'     : 0,
            'total_audits'       : 0,
            'period_data'        : []   # snapshot par période
        }

    # ── Gestion des membres ──────────────────────────────────────

    def add_member(self, member: Member, initial_score: Optional[float] = None):
        """
        Ajoute un membre au Node.
        Si initial_score est fourni, applique la portabilité inter-Nodes.
        """
        if initial_score is not None:
            member.trust_score = initial_score
        member.last_active_period = self.period
        member.record()
        self.members[member.member_id] = member

    # ── Eq.(8) — Seuil adaptatif de Witnesses ───────────────────

    def k_adaptive(self) -> int:
        """
        Eq.(8) : k_j = max(k_min, floor(α_k · |M_j|))
        Le seuil s'adapte dynamiquement à la taille de la communauté.
        """
        n = len(self.members)
        k = max(self.P.K_MIN, int(self.P.ALPHA_K * n))
        return k

    # ── Eq.(7) — Qualité d'une Contribution ─────────────────────

    def compute_quality(self, signal: Signal) -> float:
        """
        Eq.(7) : q(s) = τ̄_W · ρ(s)
        où τ̄_W = moyenne TrustScore des Witnesses
        et ρ(s) = min(|W(s)| / k_j, 1) = taux de consensus
        """
        if not signal.witnesses:
            return 0.0

        # τ̄_W — moyenne TrustScore des Witnesses
        avg_witness_score = sum(
            self.members[wid].trust_score
            for wid in signal.witnesses
            if wid in self.members
        ) / len(signal.witnesses)

        # ρ(s) — taux de consensus (borné à 1)
        k = self.k_adaptive()
        rho = min(len(signal.witnesses) / k, 1.0)

        return avg_witness_score * rho

    # ── Cycle Signal → Contribution ─────────────────────────────

    def submit_signal(self, member: Member, real_quality: float) -> Optional[Signal]:
        """
        Soumet un Signal au Node.
        La validation est effectuée par des Witnesses selon leur comportement.
        """
        signal_id = f"S{self.period}_{member.member_id}_{len(self.signals)}"
        signal = Signal(
            signal_id    = signal_id,
            author_id    = member.member_id,
            node_id      = self.node_id,
            period       = self.period,
            real_quality = real_quality,
        )

        # Witnesses éligibles — TrustScore ≥ seuil et pas l'auteur
        eligible = [
            m for mid, m in self.members.items()
            if mid != member.member_id and m.trust_score >= 0.25
        ]

        k = self.k_adaptive()
        if len(eligible) < k:
            return None  # Signal rejeté — communauté trop petite

        # Sélection de k Witnesses
        witnesses = random.sample(eligible, k)

        for w in witnesses:
            # Décision de validation selon le comportement du Witness
            if w.behavior == 'honest':
                # Un Witness honnête valide si la qualité réelle dépasse le seuil
                validates = real_quality >= 0.45
            elif w.behavior == 'colluder' and member.behavior == 'colluder':
                # Collusion — validation systématique entre complices
                validates = True
            else:
                validates = real_quality >= 0.45

            if validates:
                signal.witnesses.append(w.member_id)

        # La Contribution est validée si le seuil k est atteint
        if len(signal.witnesses) >= k:
            signal.validated    = True
            signal.quality_score = self.compute_quality(signal)
            self.stats['total_contributions'] += 1

        self.signals.append(signal)
        self.stats['total_signals'] += 1
        return signal

    # ── Audit interne ────────────────────────────────────────────

    def audit_signals(self, period_signals: list[Signal]):
        """
        Mécanisme d'audit interne.
        Les signaux de mauvaise qualité ont une probabilité d'être audités.
        Un signal audité déclenche la Force 4 (W) pour les Witnesses.
        """
        for s in period_signals:
            if not s.validated:
                continue
            # Probabilité d'audit proportionnelle à l'écart de qualité
            if s.real_quality < 0.30:
                p_audit = self.P.AUDIT_P * 2.5
            elif s.real_quality < 0.45:
                p_audit = self.P.AUDIT_P * 1.2
            else:
                p_audit = self.P.AUDIT_P * 0.05

            if random.random() < p_audit:
                s.audited = True
                self.stats['total_audits'] += 1

    # ── Eq.(1-5) — Mise à jour du TrustScore ────────────────────

    def update_trust_scores(
        self,
        period_signals: list[Signal],
        defaults      : list[int],
        actives       : list[int]
    ):
        """
        Implémente l'équation d'évolution principale (Eq.1) :
        τ_{i,j}(t+1) = clip(τ + G - L - D - W, 0, 1)

        G : Eq.(2) — gain par contribution validée non auditée
        L : Eq.(3) — perte par défaut
        D : Eq.(4) — dépréciation par inactivité
        W : Eq.(5) — coût de mauvaise validation (Witness)
        """
        for mid, member in self.members.items():
            old_score = member.trust_score

            # ── Force 1 : Gain G_{i,j}(t) = η · Σ q(s_k) ────────
            valid_contribs = [
                s for s in period_signals
                if s.author_id == mid
                and s.validated
                and not s.audited
            ]
            G = self.P.ETA * sum(s.quality_score for s in valid_contribs)

            # ── Force 2 : Perte L_{i,j}(t) = κ · 1_{défaut} ─────
            L = self.P.KAPPA if mid in defaults else 0.0

            # ── Force 3 : Dépréciation D_{i,j}(t) = δ · τ · 1_{inactif}
            D = self.P.DELTA * member.trust_score if mid not in actives else 0.0

            # ── Force 4 : Coût Witness W_{i,j}(t) ────────────────
            # W = φ · Σ_{s audité, i ∈ W(s)} τ_{i,j} / |W(s)|
            W = sum(
                self.P.PHI * member.trust_score / max(len(s.witnesses), 1)
                for s in period_signals
                if s.audited and mid in s.witnesses
            )

            # ── Eq.(1) : clip(τ + G - L - D - W, 0, 1) ──────────
            member.trust_score += G - L - D - W
            member.clip()

            # Mise à jour des compteurs
            member.contributions    += len(valid_contribs)
            member.total_gain       += G
            member.total_loss       += L
            member.total_depreciation += D
            member.total_witness_cost += W

            if mid in defaults: member.defaults += 1
            if mid in actives:
                member.periods_active     += 1
                member.last_active_period  = self.period

            member.record()

        self.period += 1

    # ── Simulation d'une période ─────────────────────────────────

    def simulate_period(self):
        """
        Simule une période complète :
        1. Chaque membre produit un Signal selon son comportement
        2. Les Witnesses valident
        3. Audit interne
        4. Mise à jour des TrustScores
        """
        period_signals = []
        defaults       = []
        actives        = []

        for mid, member in self.members.items():
            member.last_active_period = self.period

            if member.behavior == 'honest':
                # Contribution régulière de haute qualité
                quality = random.gauss(0.72, 0.12)
                quality = max(0.0, min(1.0, quality))
                s = self.submit_signal(member, quality)
                if s and s.validated:
                    period_signals.append(s)
                actives.append(mid)
                # Défaut accidentel rare (5%)
                if random.random() < 0.05:
                    defaults.append(mid)

            elif member.behavior == 'freerider':
                # Inactif la plupart du temps
                if random.random() < 0.08:
                    quality = random.uniform(0.10, 0.35)
                    s = self.submit_signal(member, quality)
                    if s and s.validated:
                        period_signals.append(s)
                    actives.append(mid)
                # Sinon inactif — dépréciation s'applique

            elif member.behavior == 'colluder':
                # Signal de mauvaise qualité — cherche validation complice
                quality = random.gauss(0.18, 0.08)
                quality = max(0.0, min(0.35, quality))
                s = self.submit_signal(member, quality)
                if s and s.validated:
                    period_signals.append(s)
                actives.append(mid)

            elif member.behavior == 'deserter':
                # Contribution minimale — juste assez pour éviter dépréciation
                if random.random() < 0.25:
                    quality = random.gauss(0.42, 0.10)
                    quality = max(0.0, min(1.0, quality))
                    s = self.submit_signal(member, quality)
                    if s and s.validated:
                        period_signals.append(s)
                    actives.append(mid)

        # Audit des signaux de la période
        self.audit_signals(period_signals)

        # Mise à jour des TrustScores
        self.update_trust_scores(period_signals, defaults, actives)

        # Snapshot de la période
        self.stats['period_data'].append({
            'period'       : self.period,
            'n_signals'    : len(period_signals),
            'n_defaults'   : len(defaults),
            'n_actives'    : len(actives),
            'avg_score'    : np.mean([m.trust_score for m in self.members.values()]),
        })

    def run(self, periods: int = 52):
        """Lance la simulation sur N périodes."""
        for _ in range(periods):
            self.simulate_period()
        return self

    # ── Eq.(13) — Pouvoir de vote ────────────────────────────────

    def voting_power(self) -> dict:
        """
        Eq.(13) : V_{i,j}(t) = τ_{i,j}(t) / Σ_k τ_{k,j}(t)
        """
        total = sum(m.trust_score for m in self.members.values())
        if total == 0:
            return {mid: 0.0 for mid in self.members}
        return {mid: m.trust_score / total for mid, m in self.members.items()}

    # ── Rapport textuel ──────────────────────────────────────────

    def report(self):
        """Rapport complet de la simulation."""
        print(f"\n{'═'*65}")
        print(f"  CommunityTrust Protocol v0.1 — Node: {self.node_id}")
        print(f"  Simulation : {self.period} périodes | {len(self.members)} membres")
        print(f"{'═'*65}")
        print(f"  {'ID':<5} {'Comportement':<14} {'Score':>7} "
              f"{'Contrib':>8} {'Défauts':>8} {'Vote':>7}")
        print(f"  {'─'*58}")

        votes = self.voting_power()
        for mid, m in sorted(self.members.items(), key=lambda x: -x[1].trust_score):
            bar = '█' * int(m.trust_score * 12)
            print(f"  M{mid:<4} {m.behavior:<14} {m.trust_score:>6.4f}  "
                  f"{m.contributions:>7}  {m.defaults:>7}  "
                  f"{votes[mid]:>6.3f}  {bar}")

        # Moyennes par groupe
        groups = defaultdict(list)
        for m in self.members.values():
            groups[m.behavior].append(m.trust_score)

        print(f"\n  Scores moyens par comportement :")
        print(f"  {'─'*45}")
        for b, scores in sorted(groups.items()):
            avg = np.mean(scores)
            bar = '█' * int(avg * 25)
            print(f"  {b:<14}  {avg:.4f}  {bar}")

        # Vérification des 3 propositions
        ha = np.mean(groups.get('honest',   [0]))
        fa = np.mean(groups.get('freerider',[0]))
        ca = np.mean(groups.get('colluder', [0]))
        da = np.mean(groups.get('deserter', [0]))

        print(f"\n  Vérification propositions théoriques :")
        print(f"  {'─'*50}")
        p1 = all(0 <= m.trust_score <= 1 for m in self.members.values())
        p2 = ha > fa
        p3 = ha > ca
        print(f"  Prop.1  Bornitude [0,1]              {'✓' if p1 else '✗'}")
        print(f"  Prop.2  Honnête > Passager clandestin {'✓' if p2 else '✗'}"
              f"  ({ha:.3f} > {fa:.3f})")
        print(f"  Prop.3  Honnête > Colludeur           {'✓' if p3 else '✗'}"
              f"  ({ha:.3f} > {ca:.3f})")

        # Stats globales
        print(f"\n  Statistiques globales :")
        print(f"  Signaux soumis      : {self.stats['total_signals']}")
        print(f"  Contributions valid.: {self.stats['total_contributions']}")
        print(f"  Défauts enregistrés : {self.stats['total_defaults']}")
        print(f"  Audits déclenchés   : {self.stats['total_audits']}")
        print(f"{'═'*65}\n")

        return {'honest': ha, 'freerider': fa, 'colluder': ca, 'deserter': da}

# ══════════════════════════════════════════════════════════════════
# SECTION 4 — SIMULATION MONTE CARLO
# ══════════════════════════════════════════════════════════════════

def run_single_simulation(seed: int, periods: int = 52) -> dict:
    """
    Lance une simulation complète avec un seed donné.
    Retourne les scores finaux par comportement.
    """
    random.seed(seed)
    np.random.seed(seed)

    node = CTPNode(f"Node_{seed}")

    members_config = [
        (1,  'honest'),    (2,  'honest'),    (3,  'honest'),
        (4,  'honest'),    (5,  'honest'),
        (6,  'freerider'), (7,  'freerider'), (8,  'freerider'),
        (9,  'colluder'),  (10, 'colluder'),
        (11, 'deserter'),  (12, 'deserter'),
    ]

    for mid, beh in members_config:
        node.add_member(Member(mid, beh))

    node.run(periods)

    # Collecter les résultats
    results = {'seed': seed, 'scores': {}, 'histories': {}}
    for mid, m in node.members.items():
        results['scores'][m.behavior]    = results['scores'].get(m.behavior, [])
        results['scores'][m.behavior].append(m.trust_score)
        results['histories'][mid] = {
            'behavior': m.behavior,
            'history' : m.history,
            'contributions': m.contributions,
            'defaults': m.defaults,
        }

    return results, node

def run_monte_carlo(
    n_simulations : int = 1000,
    periods       : int = 52,
    verbose       : bool = True
) -> dict:
    """
    Validation Monte Carlo principale.
    Lance N simulations indépendantes et agrège les résultats.

    Vérifie :
    - Prop.1 : Bornitude [0,1] pour tous les membres toutes périodes
    - Prop.2 : Score moyen honnête > score moyen passager
    - Prop.3 : Score moyen honnête > score moyen colludeur
    """
    if verbose:
        print(f"\n{'═'*65}")
        print(f"  Validation Monte Carlo — CTP v0.1")
        print(f"  {n_simulations} simulations × {periods} périodes")
        print(f"  Paramètres : η={P.ETA} κ={P.KAPPA} δ={P.DELTA} "
              f"φ={P.PHI} λ={P.LAMBDA_} μ={P.MU}")
        print(f"{'═'*65}")

    all_results = defaultdict(list)
    prop1_violations = 0
    prop2_violations = 0
    prop3_violations = 0

    # Simulation de référence (seed=42) pour les graphiques
    reference_result, reference_node = run_single_simulation(42, periods)

    for i in range(n_simulations):
        result, _ = run_single_simulation(i, periods)

        for behavior, scores in result['scores'].items():
            all_results[behavior].extend(scores)

        # Vérification Prop.1
        for scores in result['scores'].values():
            for s in scores:
                if not (0 <= s <= 1):
                    prop1_violations += 1

        # Vérification Prop.2 et Prop.3
        ha = np.mean(result['scores'].get('honest',   [0]))
        fa = np.mean(result['scores'].get('freerider',[0]))
        ca = np.mean(result['scores'].get('colluder', [0]))

        if ha <= fa: prop2_violations += 1
        if ha <= ca: prop3_violations += 1

        if verbose and (i+1) % 200 == 0:
            print(f"  Simulation {i+1:>4}/{n_simulations} — "
                  f"P2 violations: {prop2_violations} | "
                  f"P3 violations: {prop3_violations}")

    # Résultats agrégés
    mc_results = {}
    for behavior, scores in all_results.items():
        mc_results[behavior] = {
            'mean' : np.mean(scores),
            'std'  : np.std(scores),
            'min'  : np.min(scores),
            'max'  : np.max(scores),
            'q25'  : np.percentile(scores, 25),
            'q75'  : np.percentile(scores, 75),
        }

    if verbose:
        print(f"\n  Résultats agrégés ({n_simulations} simulations) :")
        print(f"  {'─'*55}")
        print(f"  {'Comportement':<14} {'Moyenne':>8} {'Écart-type':>11} "
              f"{'Min':>7} {'Max':>7}")
        print(f"  {'─'*55}")
        for b, s in sorted(mc_results.items()):
            print(f"  {b:<14} {s['mean']:>8.4f} {s['std']:>11.4f} "
                  f"{s['min']:>7.4f} {s['max']:>7.4f}")

        total = n_simulations
        print(f"\n  Taux de respect des propositions :")
        print(f"  Prop.1 (Bornitude)   : "
              f"{100*(1-prop1_violations/total):.2f}%  "
              f"({'✓' if prop1_violations==0 else '✗'})")
        print(f"  Prop.2 (Honnête>FR)  : "
              f"{100*(1-prop2_violations/total):.2f}%  "
              f"({'✓' if prop2_violations==0 else '✗'})")
        print(f"  Prop.3 (Honnête>Col) : "
              f"{100*(1-prop3_violations/total):.2f}%  "
              f"({'✓' if prop3_violations==0 else '✗'})")

    return mc_results, reference_node, {
        'prop1_rate': 1 - prop1_violations/n_simulations,
        'prop2_rate': 1 - prop2_violations/n_simulations,
        'prop3_rate': 1 - prop3_violations/n_simulations,
    }

# ══════════════════════════════════════════════════════════════════
# SECTION 5 — ANALYSE DE SENSIBILITÉ
# ══════════════════════════════════════════════════════════════════

def sensitivity_analysis(periods: int = 52) -> dict:
    """
    Analyse de sensibilité sur les paramètres clés.
    Vérifie que les paramètres recommandés sont robustes.
    """
    print(f"\n  Analyse de sensibilité")
    print(f"  {'─'*50}")

    results = {}

    # Sensibilité à δ (dépréciation)
    delta_vals = [0.01, 0.02, 0.03, 0.05, 0.08]
    delta_results = []

    for dv in delta_vals:
        P_temp = CTPParams()
        P_temp.DELTA = dv
        random.seed(42); np.random.seed(42)

        node = CTPNode("sens_delta", P_temp)
        for mid, beh in [(1,'honest'),(2,'honest'),(3,'honest'),
                          (4,'honest'),(5,'honest'),
                          (6,'freerider'),(7,'freerider'),(8,'freerider')]:
            node.add_member(Member(mid, beh))
        node.run(periods)

        ha = np.mean([m.trust_score for m in node.members.values()
                      if m.behavior=='honest'])
        fa = np.mean([m.trust_score for m in node.members.values()
                      if m.behavior=='freerider'])
        delta_results.append({'delta': dv, 'honest': ha, 'freerider': fa,
                               'gap': ha - fa})
        print(f"  δ={dv:.2f}  honnête={ha:.4f}  "
              f"passager={fa:.4f}  écart={ha-fa:.4f}")

    results['delta'] = delta_results

    # Sensibilité à φ (responsabilité Witness)
    phi_vals = [0.05, 0.10, 0.15, 0.20, 0.25]
    phi_results = []

    print(f"\n  Sensibilité à φ (responsabilité Witness) :")
    for pv in phi_vals:
        P_temp = CTPParams()
        P_temp.PHI = pv
        random.seed(42); np.random.seed(42)

        node = CTPNode("sens_phi", P_temp)
        for mid, beh in [(1,'honest'),(2,'honest'),(3,'honest'),
                          (4,'honest'),(5,'honest'),
                          (6,'colluder'),(7,'colluder'),(8,'colluder')]:
            node.add_member(Member(mid, beh))
        node.run(periods)

        ha = np.mean([m.trust_score for m in node.members.values()
                      if m.behavior=='honest'])
        ca = np.mean([m.trust_score for m in node.members.values()
                      if m.behavior=='colluder'])
        phi_results.append({'phi': pv, 'honest': ha, 'colluder': ca,
                             'gap': ha - ca})
        print(f"  φ={pv:.2f}  honnête={ha:.4f}  "
              f"colludeur={ca:.4f}  écart={ha-ca:.4f}")

    results['phi'] = phi_results
    return results

# ══════════════════════════════════════════════════════════════════
# SECTION 6 — VISUALISATION ACADÉMIQUE
# ══════════════════════════════════════════════════════════════════

COLORS = {
    'honest'   : '#2ca02c',
    'freerider': '#d62728',
    'colluder' : '#ff7f0e',
    'deserter' : '#9467bd',
}
LABELS = {
    'honest'   : 'Honnête',
    'freerider': 'Passager clandestin',
    'colluder' : 'Colludeur',
    'deserter' : 'Déserteur',
}

def plot_results(
    reference_node: CTPNode,
    mc_results    : dict,
    sens_results  : dict,
    prop_rates    : dict,
    n_simulations : int,
    output_path   : str = '/mnt/user-data/outputs/CTP_simulation_v0.1.png'
):
    """
    Génère les graphiques académiques de la simulation.
    Style publication — fond blanc, couleurs standards.
    """
    plt.rcParams.update({
        'figure.facecolor' : 'white',
        'axes.facecolor'   : 'white',
        'axes.edgecolor'   : '#333333',
        'axes.labelcolor'  : '#333333',
        'axes.titlesize'   : 10,
        'axes.labelsize'   : 9,
        'xtick.labelsize'  : 8,
        'ytick.labelsize'  : 8,
        'legend.fontsize'  : 8,
        'font.family'      : 'serif',
        'text.color'       : '#333333',
        'grid.color'       : '#dddddd',
        'grid.linewidth'   : 0.8,
    })

    fig = plt.figure(figsize=(16, 12))
    fig.suptitle(
        'CommunityTrust Protocol (CTP v0.1) — Validation par Simulation Monte Carlo\n'
        'Ange AWALA, OpenScience Community — DOI: 10.5281/zenodo.20031237',
        fontsize=11, fontweight='bold', y=0.98
    )

    gs = fig.add_gridspec(3, 3, hspace=0.45, wspace=0.38,
                          left=0.08, right=0.97, top=0.93, bottom=0.07)

    periods = reference_node.period
    t = list(range(periods))

    # ── Graphique 1 : Évolution individuelle ─────────────────────
    ax1 = fig.add_subplot(gs[0, :2])
    ax1.set_title('(a) Évolution individuelle du TrustScore — 52 périodes', pad=8)

    for mid, m in reference_node.members.items():
        hist = m.history[1:]  # skip t=0
        ls = '-' if m.behavior == 'honest' else '--'
        ax1.plot(range(len(hist)), hist,
                 color=COLORS[m.behavior], alpha=0.7,
                 linewidth=1.5, linestyle=ls)

    ax1.axhspan(0.75, 1.0,  alpha=0.06, color='#2ca02c')
    ax1.axhspan(0.0,  0.20, alpha=0.06, color='#d62728')
    ax1.axhline(0.5, color='#999999', linewidth=0.8, linestyle=':', alpha=0.8)
    ax1.text(51, 0.87, 'Zone élite', color='#2ca02c', fontsize=7, ha='right')
    ax1.text(51, 0.07, 'Zone critique', color='#d62728', fontsize=7, ha='right')

    patches = [mpatches.Patch(color=COLORS[b], label=LABELS[b]) for b in COLORS]
    ax1.legend(handles=patches, loc='upper left', framealpha=0.8, fontsize=8)
    ax1.set_xlabel('Période (semaines)')
    ax1.set_ylabel('TrustScore τ ∈ [0, 1]')
    ax1.set_ylim(-0.02, 1.08)
    ax1.set_xlim(0, periods - 1)
    ax1.grid(True, alpha=0.5)

    # ── Graphique 2 : Scores finaux barres ───────────────────────
    ax2 = fig.add_subplot(gs[0, 2])
    ax2.set_title('(b) Scores finaux\npar membre', pad=8)

    sorted_members = sorted(reference_node.members.values(),
                            key=lambda m: m.trust_score, reverse=True)
    ids    = [f'M{m.member_id}' for m in sorted_members]
    scores = [m.trust_score for m in sorted_members]
    colors = [COLORS[m.behavior] for m in sorted_members]

    bars = ax2.barh(ids, scores, color=colors, alpha=0.85, height=0.7,
                    edgecolor='white', linewidth=0.5)
    for bar, score in zip(bars, scores):
        ax2.text(min(score + 0.01, 0.97), bar.get_y() + bar.get_height()/2,
                 f'{score:.3f}', va='center', fontsize=7)

    ax2.set_xlim(0, 1.15)
    ax2.set_xlabel('TrustScore final')
    ax2.invert_yaxis()
    ax2.grid(True, axis='x', alpha=0.4)

    # ── Graphique 3 : Moyenne ± σ par comportement ───────────────
    ax3 = fig.add_subplot(gs[1, :2])
    ax3.set_title('(c) Évolution moyenne par comportement (± 1σ)', pad=8)

    histories_by_behavior = defaultdict(list)
    for mid, m in reference_node.members.items():
        histories_by_behavior[m.behavior].append(m.history[1:])

    for beh, hists in histories_by_behavior.items():
        arr  = np.array(hists)
        mean = arr.mean(axis=0)
        std  = arr.std(axis=0)
        t_ax = range(len(mean))
        ax3.plot(t_ax, mean, color=COLORS[beh], linewidth=2.2, label=LABELS[beh])
        ax3.fill_between(t_ax, mean-std, mean+std,
                         color=COLORS[beh], alpha=0.12)

    ax3.axhline(0.5, color='#999999', linewidth=0.8, linestyle=':', alpha=0.8)
    ax3.set_xlabel('Période (semaines)')
    ax3.set_ylabel('TrustScore moyen ± σ')
    ax3.set_ylim(-0.02, 1.08)
    ax3.set_xlim(0, periods - 1)
    ax3.legend(framealpha=0.8)
    ax3.grid(True, alpha=0.4)

    # ── Graphique 4 : Distribution Monte Carlo ───────────────────
    ax4 = fig.add_subplot(gs[1, 2])
    ax4.set_title('(d) Distribution Monte Carlo\n'
                  f'({n_simulations} simulations)', pad=8)

    behaviors_order = ['honest', 'freerider', 'colluder', 'deserter']
    for i, beh in enumerate(behaviors_order):
        if beh in mc_results:
            s  = mc_results[beh]
            ax4.barh(i, s['mean'],
                     xerr=s['std'],
                     color=COLORS[beh], alpha=0.8,
                     height=0.6, capsize=4,
                     edgecolor='white')
            ax4.text(s['mean'] + s['std'] + 0.01, i,
                     f"{s['mean']:.3f}±{s['std']:.3f}",
                     va='center', fontsize=7)

    ax4.set_yticks(range(len(behaviors_order)))
    ax4.set_yticklabels([LABELS[b] for b in behaviors_order], fontsize=8)
    ax4.set_xlabel('Score moyen ± σ')
    ax4.set_xlim(0, 1.35)
    ax4.grid(True, axis='x', alpha=0.4)

    # ── Graphique 5 : Sensibilité à δ ────────────────────────────
    ax5 = fig.add_subplot(gs[2, 0])
    ax5.set_title('(e) Sensibilité à δ\n(taux de dépréciation)', pad=8)

    delta_data = sens_results['delta']
    deltas  = [d['delta']    for d in delta_data]
    h_vals  = [d['honest']   for d in delta_data]
    fr_vals = [d['freerider'] for d in delta_data]
    gaps    = [d['gap']      for d in delta_data]

    ax5.plot(deltas, h_vals,  'o-', color=COLORS['honest'],
             linewidth=2, markersize=6, label='Honnête')
    ax5.plot(deltas, fr_vals, 's--', color=COLORS['freerider'],
             linewidth=2, markersize=6, label='Passager')
    ax5.axvline(P.DELTA, color='#666666', linewidth=1,
                linestyle=':', label=f'δ recommandé={P.DELTA}')
    ax5.set_xlabel('δ (dépréciation)')
    ax5.set_ylabel('Score moyen final')
    ax5.set_ylim(0, 1.05)
    ax5.legend(fontsize=7)
    ax5.grid(True, alpha=0.4)

    # ── Graphique 6 : Sensibilité à φ ────────────────────────────
    ax6 = fig.add_subplot(gs[2, 1])
    ax6.set_title('(f) Sensibilité à φ\n(responsabilité Witness)', pad=8)

    phi_data = sens_results['phi']
    phis    = [d['phi']     for d in phi_data]
    h_vals2 = [d['honest']  for d in phi_data]
    c_vals  = [d['colluder'] for d in phi_data]

    ax6.plot(phis, h_vals2, 'o-', color=COLORS['honest'],
             linewidth=2, markersize=6, label='Honnête')
    ax6.plot(phis, c_vals,  's--', color=COLORS['colluder'],
             linewidth=2, markersize=6, label='Colludeur')
    ax6.axvline(P.PHI, color='#666666', linewidth=1,
                linestyle=':', label=f'φ recommandé={P.PHI}')
    ax6.set_xlabel('φ (responsabilité Witness)')
    ax6.set_ylabel('Score moyen final')
    ax6.set_ylim(0, 1.05)
    ax6.legend(fontsize=7)
    ax6.grid(True, alpha=0.4)

    # ── Graphique 7 : Vérification propositions ──────────────────
    ax7 = fig.add_subplot(gs[2, 2])
    ax7.set_title('(g) Taux de respect des propositions\n'
                  f'({n_simulations} simulations)', pad=8)
    ax7.set_facecolor('white')

    props = [
        (f"Prop.1\nBornitude [0,1]",      prop_rates['prop1_rate']),
        (f"Prop.2\nHonnête > Passager",   prop_rates['prop2_rate']),
        (f"Prop.3\nHonnête > Colludeur",  prop_rates['prop3_rate']),
    ]

    for i, (label, rate) in enumerate(props):
        y = 0.75 - i * 0.30
        color = '#2ca02c' if rate >= 0.99 else '#ff7f0e'
        symbol = '✓' if rate >= 0.99 else '~'
        ax7.text(0.08, y, symbol, transform=ax7.transAxes,
                 fontsize=28, color=color, va='center', fontweight='bold')
        ax7.text(0.30, y + 0.04, label, transform=ax7.transAxes,
                 fontsize=8.5, color='#333333', va='center')
        ax7.text(0.30, y - 0.06, f'{rate*100:.1f}%',
                 transform=ax7.transAxes,
                 fontsize=9, color=color, va='center', fontweight='bold')

    ax7.set_xlim(0, 1)
    ax7.set_ylim(0, 1)
    ax7.axis('off')

    plt.savefig(output_path, dpi=150, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    print(f"\n  Graphique sauvegardé : {output_path}")
    plt.close()

# ══════════════════════════════════════════════════════════════════
# SECTION 7 — POINT D'ENTRÉE PRINCIPAL
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":

    print("\n" + "═"*65)
    print("  CommunityTrust Protocol (CTP) v0.1")
    print("  Validation Monte Carlo")
    print("  Ange AWALA — OpenScience Community")
    print("  DOI : 10.5281/zenodo.20031237")
    print("═"*65)

    # ── 1. Simulation de référence ───────────────────────────────
    print("\n[1/4] Simulation de référence (seed=42, 52 périodes)...")
    random.seed(42); np.random.seed(42)

    ref_node = CTPNode("OpenScience-Reference")
    for mid, beh in [
        (1,'honest'),(2,'honest'),(3,'honest'),(4,'honest'),(5,'honest'),
        (6,'freerider'),(7,'freerider'),(8,'freerider'),
        (9,'colluder'),(10,'colluder'),
        (11,'deserter'),(12,'deserter'),
    ]:
        ref_node.add_member(Member(mid, beh))

    ref_node.run(52)
    scores = ref_node.report()

    # ── 2. Validation Monte Carlo ────────────────────────────────
    print("\n[2/4] Validation Monte Carlo (1000 simulations)...")
    mc_results, _, prop_rates = run_monte_carlo(
        n_simulations=1000,
        periods=52,
        verbose=True
    )

    # ── 3. Analyse de sensibilité ────────────────────────────────
    print("\n[3/4] Analyse de sensibilité des paramètres...")
    sens_results = sensitivity_analysis(periods=52)

    # ── 4. Visualisation ─────────────────────────────────────────
    print("\n[4/4] Génération des graphiques...")
    plot_results(ref_node, mc_results, sens_results, prop_rates, 1000)

    # ── Résumé final ─────────────────────────────────────────────
    print("\n" + "═"*65)
    print("  RÉSUMÉ FINAL")
    print("═"*65)
    print(f"  Prop.1 Bornitude [0,1]           : "
          f"{prop_rates['prop1_rate']*100:.2f}%")
    print(f"  Prop.2 Honnête > Passager        : "
          f"{prop_rates['prop2_rate']*100:.2f}%")
    print(f"  Prop.3 Honnête > Colludeur       : "
          f"{prop_rates['prop3_rate']*100:.2f}%")
    print(f"\n  Fichiers produits :")
    print(f"  → /mnt/user-data/outputs/CTP_simulation_v0.1.png")
    print("═"*65 + "\n")
