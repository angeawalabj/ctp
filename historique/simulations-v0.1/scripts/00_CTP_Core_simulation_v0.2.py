"""
CommunityTrust Protocol (CTP) - Simulation v0.2
Corrections issues de la v0.1 :
  - Colludeur puni même sans challenge externe (audit interne)
  - Seuil de Witnesses adaptatif selon taille du Node
  - Comportement honnête stable même en petite communauté
"""

import random
import math
from dataclasses import dataclass, field
from collections import defaultdict

# ─────────────────────────────────────────
# PARAMÈTRES
# ─────────────────────────────────────────
ETA   = 0.05
KAPPA = 0.15
DELTA = 0.02
PHI   = 0.15
LAMBDA= 0.20
MU    = 0.70
K_MIN = 3
AUDIT_RATE = 0.15  # probabilité d'audit interne par période

# ─────────────────────────────────────────
# STRUCTURES
# ─────────────────────────────────────────

@dataclass
class Member:
    id: int
    behavior: str
    trust_score: float = 0.3
    contributions: int = 0
    defaults: int = 0
    periods_active: int = 0
    history: list = field(default_factory=list)

    def clip(self):
        self.trust_score = max(0.0, min(1.0, self.trust_score))

@dataclass
class Signal:
    author_id: int
    real_quality: float
    period: int
    validated: bool = False
    witnesses: list = field(default_factory=list)
    quality_score: float = 0.0
    audited: bool = False

# ─────────────────────────────────────────
# NODE CTP v2
# ─────────────────────────────────────────

class CTPNode:
    def __init__(self, node_id: str):
        self.node_id = node_id
        self.members: dict[int, Member] = {}
        self.signals: list[Signal] = []
        self.period = 0

    def add_member(self, m: Member):
        self.members[m.id] = m

    def _k_adaptive(self) -> int:
        """Seuil adaptatif — au moins 3 ou 20% de la communauté"""
        return max(K_MIN, int(len(self.members) * 0.20))

    def _eligible_witnesses(self, exclude_id: int) -> list:
        return [m for mid, m in self.members.items()
                if mid != exclude_id and m.trust_score >= 0.25]

    def _quality(self, signal: Signal) -> float:
        if not signal.witnesses:
            return 0.0
        avg_tau = sum(self.members[w].trust_score for w in signal.witnesses) / len(signal.witnesses)
        k_eff = len(signal.witnesses)
        k_req = self._k_adaptive()
        rho = min(k_eff / k_req, 1.0)
        return avg_tau * rho

    def _submit(self, member: Member, real_quality: float) -> Signal:
        signal = Signal(author_id=member.id, real_quality=real_quality, period=self.period)
        eligible = self._eligible_witnesses(member.id)
        k = self._k_adaptive()

        if len(eligible) < k:
            return signal

        witnesses = random.sample(eligible, k)
        for w in witnesses:
            if w.behavior == 'honest':
                validates = real_quality >= 0.45
            elif w.behavior == 'colluder' and member.behavior == 'colluder':
                validates = True
            else:
                validates = real_quality >= 0.45

            if validates:
                signal.witnesses.append(w.id)

        if len(signal.witnesses) >= k:
            signal.validated = True
            signal.quality_score = self._quality(signal)

        self.signals.append(signal)
        return signal

    def _audit(self, signal: Signal) -> bool:
        """Audit interne — détecte les validations de mauvaise qualité"""
        if signal.real_quality < 0.3 and signal.validated:
            return random.random() < AUDIT_RATE * 2
        return random.random() < AUDIT_RATE * 0.1

    def _update(self, period_signals: list, defaults: list, actives: list):
        # Audit des signaux de cette période
        for s in period_signals:
            if self._audit(s):
                s.audited = True

        for mid, m in self.members.items():
            # Gain — contributions validées non auditées
            valid_contribs = [s for s in period_signals
                              if s.author_id == mid and s.validated and not s.audited]
            G = ETA * sum(s.quality_score for s in valid_contribs)

            # Perte — défaut
            L = KAPPA if mid in defaults else 0.0

            # Dépréciation — inactivité
            D = DELTA * m.trust_score if mid not in actives else 0.0

            # Coût Witness — avoir validé un Signal audité
            witness_cost = 0.0
            for s in period_signals:
                if s.audited and mid in s.witnesses:
                    witness_cost += PHI * m.trust_score / max(len(s.witnesses), 1)

            m.trust_score += G - L - D - witness_cost
            m.clip()

            m.contributions += len(valid_contribs)
            if mid in defaults: m.defaults += 1
            if mid in actives:  m.periods_active += 1
            m.history.append(round(m.trust_score, 4))

        self.period += 1

    def run(self, periods: int = 52):
        for t in range(periods):
            period_signals = []
            defaults, actives = [], []

            for mid, m in self.members.items():
                if m.behavior == 'honest':
                    quality = random.uniform(0.55, 1.0)
                    s = self._submit(m, quality)
                    if s.validated: period_signals.append(s)
                    actives.append(mid)
                    if random.random() < 0.05: defaults.append(mid)

                elif m.behavior == 'freerider':
                    if random.random() < 0.08:
                        s = self._submit(m, random.uniform(0.1, 0.35))
                        if s.validated: period_signals.append(s)
                        actives.append(mid)

                elif m.behavior == 'colluder':
                    quality = random.uniform(0.1, 0.25)
                    s = self._submit(m, quality)
                    if s.validated: period_signals.append(s)
                    actives.append(mid)

                elif m.behavior == 'deserter':
                    if random.random() < 0.25:
                        s = self._submit(m, random.uniform(0.3, 0.55))
                        if s.validated: period_signals.append(s)
                        actives.append(mid)

            self._update(period_signals, defaults, actives)
        return self

    def report(self, periods: int):
        print(f"\n{'='*60}")
        print(f"  CTP v0.2 — Node: {self.node_id} — {periods} périodes")
        print(f"{'='*60}")
        print(f"  {'ID':<6} {'Type':<12} {'Score':>7} {'Contribs':>9} {'Défauts':>8}")
        print(f"  {'-'*48}")
        for mid, m in sorted(self.members.items(), key=lambda x: -x[1].trust_score):
            bar = '█' * int(m.trust_score * 15)
            print(f"  M{mid:<5} {m.behavior:<12} {m.trust_score:>6.4f}  {m.contributions:>8}  {m.defaults:>8}  {bar}")
        print(f"{'='*60}")

        groups = defaultdict(list)
        for m in self.members.values():
            groups[m.behavior].append(m.trust_score)

        print(f"\n  Scores moyens par comportement :")
        print(f"  {'-'*45}")
        for b, scores in sorted(groups.items()):
            avg = sum(scores)/len(scores)
            bar = '█' * int(avg * 35)
            print(f"  {b:<12}  {avg:.4f}  {bar}")

        print(f"\n  Vérification propositions théoriques :")
        print(f"  {'-'*45}")
        ha = sum(groups['honest'])/len(groups['honest'])
        fa = sum(groups['freerider'])/len(groups['freerider'])
        ca = sum(groups['colluder'])/len(groups['colluder'])

        p1 = all(0 <= m.trust_score <= 1 for m in self.members.values())
        p2 = ha > fa
        p3 = ha > ca

        print(f"  Prop.1 Scores bornés [0,1]            {'✓' if p1 else '✗'}")
        print(f"  Prop.2 Honnête > Passager clandestin  {'✓' if p2 else '✗'}  ({ha:.3f} > {fa:.3f})")
        print(f"  Prop.3 Honnête > Colludeur            {'✓' if p3 else '✗'}  ({ha:.3f} > {ca:.3f})")

        print(f"\n  Convergence sur le temps :")
        print(f"  {'-'*45}")
        checkpoints = [0, 12, 25, 51] if periods >= 52 else [0, periods//4, periods//2, periods-1]
        for mid, m in list(self.members.items())[:4]:
            pts = [f"{m.history[t]:.2f}" for t in checkpoints if t < len(m.history)]
            print(f"  {m.behavior:<12} : {' → '.join(pts)}")
        print()

# ─────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────

if __name__ == "__main__":
    random.seed(42)

    print("\n" + "="*60)
    print("  CommunityTrust Protocol (CTP) v0.2")
    print("  'Je suis parce que nous sommes'")
    print("  OpenScience Community")
    print("="*60)
    print(f"  Paramètres : η={ETA} κ={KAPPA} δ={DELTA} φ={PHI} λ={LAMBDA} μ={MU}")
    print(f"  Audit rate : {AUDIT_RATE}")

    node = CTPNode("OpenScience-Sciences")
    members = [
        Member(1,  'honest'),
        Member(2,  'honest'),
        Member(3,  'honest'),
        Member(4,  'honest'),
        Member(5,  'honest'),
        Member(6,  'freerider'),
        Member(7,  'freerider'),
        Member(8,  'freerider'),
        Member(9,  'colluder'),
        Member(10, 'colluder'),
        Member(11, 'deserter'),
        Member(12, 'deserter'),
    ]
    for m in members:
        node.add_member(m)

    node.run(52)
    node.report(52)
