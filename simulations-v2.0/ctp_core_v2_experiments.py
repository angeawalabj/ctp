"""
CommunityTrust Protocol (CTP) — Core v2.0 : expériences reproductibles.

Produit tous les chiffres et figures de l'article CTP Core v2.0.
Chaque configuration est répétée sur plusieurs graines ; les résultats sont
rapportés en moyenne avec intervalle de confiance à 95 % (bootstrap sur les
graines).

Jeux de règles (préréglages en bas de la section Paramètres) :
  V1          règles de CTP v0.1/v1.1 telles qu'écrites ;
  V20         modèle corrigé avec les paramètres de v1.1 ;
  V21         modèle corrigé avec les paramètres recalibrés (recommandés) ;
  AUDIT_SEUL  référence sans témoins (audit aléatoire uniquement) ;
  SANS_RESP   référence avec témoins mais sans responsabilité ni sanction.

Usage (depuis n'importe quel dossier) :
  python3 ctp_core_v2_experiments.py                       # tout relancer
  python3 ctp_core_v2_experiments.py E4 E6                 # une partie
  python3 ctp_core_v2_experiments.py figures               # retracer seulement
  python3 ctp_core_v2_experiments.py DOSSIER [...]         # autre dossier de sortie
DOSSIER vaut par défaut ../article-v2.0/figures (relatif à ce script).
Dépendances : numpy, matplotlib.
"""

import json
import math
import os
import sys
from dataclasses import dataclass, replace
from multiprocessing import Pool

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

GOOD = 0.45   # seuil de qualité réelle d'un signal conforme
T = 104       # deux ans de périodes hebdomadaires


# ════════════════════════════════════════════════════════════════════
# Paramètres
# ════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class Params:
    witnesses: bool = True        # panel de témoins (False : audit seul)
    reward: str = "majority"      # "none" | "approvers" | "majority"
    audit: str = "uniform"        # "targeted" (v1.1) | "uniform"
    share_penalty: bool = False   # sanction témoin divisée par |A| (v1.1, v2.0)
    activity: str = "accepted"    # actif si "submitted" (v1.1) ou "accepted"
    eta: float = 0.02
    eta_w: float = 0.005
    kappa: float = 0.35
    kappa_s: float = 0.10
    delta: float = 0.02
    phi: float = 0.30
    p_a: float = 0.15
    q_min: float = 0.30
    k_min: int = 5
    alpha_k: float = 0.20
    theta: float = 2 / 3
    tau_w: float = 0.30
    tau0: float = 0.50
    sigma_obs: float = 0.10
    audit_err: float = 0.0
    honeypot: float = 0.05        # signaux pièges injectés par membre et par période
    appeal: bool = True           # contre-audit : sanction si deux audits concordent
    adaptive_k: bool = True       # panel réduit au nombre d'éligibles (min. 3)


V1 = Params(reward="none", audit="targeted", share_penalty=True,
            activity="submitted", eta=0.05, eta_w=0.0, kappa=0.15,
            kappa_s=0.0, phi=0.15, k_min=3, theta=1.0, honeypot=0.0,
            appeal=False, adaptive_k=False)
V20 = Params(reward="approvers", share_penalty=True, activity="submitted",
             eta=0.05, eta_w=0.01, kappa=0.15, kappa_s=0.10, phi=0.15,
             k_min=3, honeypot=0.0, appeal=False, adaptive_k=False)
V21 = Params()
AUDIT_SEUL = replace(V21, witnesses=False, honeypot=0.0, reward="none", eta_w=0.0)
SANS_RESP = replace(V21, phi=0.0, kappa_s=0.0, eta_w=0.0, reward="none",
                    honeypot=0.0)

COST_H = 0.01    # coût d'une contribution honnête (agents adaptatifs)
COST_V = 0.001   # coût d'une vérification (agents adaptatifs)


def k_of(n_others, P):
    return max(P.k_min, int(math.floor(P.alpha_k * n_others)))


def a_of(k, P):
    return int(math.ceil(P.theta * k - 1e-9))


# ════════════════════════════════════════════════════════════════════
# Simulation d'un Node
# ════════════════════════════════════════════════════════════════════
def run(P, behaviors, p_default, seed, periods=T, eps=0.1, lr=0.1):
    """behaviors : 'honest' | 'freerider' | 'colluder' | 'fraud' | 'adaptive'.
    Retourne un dict de métriques (scores finaux, trajectoires, compteurs)."""
    rng = np.random.default_rng(seed)
    n = len(behaviors)
    beh = np.array(behaviors)
    coll = beh == "colluder"
    adap = beh == "adaptive"
    tau = np.full(n, P.tau0)
    hist = np.empty((periods + 1, n)); hist[0] = tau
    k = k_of(n - 1, P)
    a_req = a_of(k, P)
    Qa = np.zeros((n, 2))   # auteur : 0 = honnête, 1 = fraude
    Qw = np.zeros((n, 2))   # témoin : 0 = vérifier, 1 = tamponner
    c = dict(bad_sub=0, bad_pass=0, good_sub=0, good_rej=0, audits=0, votes=0,
             hp=0, hp_pass=0)
    fraud_share, stamp_share = [], []

    for t in range(periods):
        dG = np.zeros(n); dR = np.zeros(n); dNeg = np.zeros(n)
        dS = np.zeros(n)
        active = np.zeros(n, bool)
        a_act = np.full(n, -1)
        w_rec = [[] for _ in range(n)]   # (action, récompense, pénalité)
        w_act = np.where(adap & (rng.random(n) < eps), rng.integers(0, 2, n),
                         np.argmax(Qw, axis=1))
        signals = []   # (auteur, Q, piège)

        for i in range(n):
            b = beh[i]
            if b == "freerider" and rng.random() >= 0.08:
                continue
            if rng.random() < p_default[i]:
                dNeg[i] += P.kappa
                active[i] = True
                continue
            if b == "adaptive":
                a = rng.integers(0, 2) if rng.random() < eps else int(np.argmax(Qa[i]))
                a_act[i] = a
                bad = a == 1
            else:
                bad = b in ("colluder", "fraud", "freerider")
            if b == "freerider":
                Q = float(rng.uniform(0.10, 0.35))
            elif bad:
                Q = float(np.clip(rng.normal(0.20, 0.08), 0, 1))
            else:
                Q = float(np.clip(rng.normal(0.72, 0.12), 0, 1))
            if P.activity == "submitted":
                active[i] = True
            signals.append((i, Q, False))
        for _ in range(rng.binomial(n, P.honeypot) if P.witnesses else 0):
            signals.append((-1, 0.10, True))

        for (i, Q, hp) in signals:
            is_bad = Q < GOOD
            if not hp:
                if is_bad: c["bad_sub"] += 1
                else: c["good_sub"] += 1
            elig = np.flatnonzero((tau >= P.tau_w) & (np.arange(n) != i))
            k_s, a_s, forced_audit = k, a_req, False
            if P.witnesses and len(elig) < k:
                if not P.adaptive_k:
                    continue
                if len(elig) >= 3:
                    k_s = len(elig); a_s = a_of(k_s, P)
                else:
                    forced_audit = True   # repli : audit systématique
            if P.witnesses and not forced_audit:
                panel = rng.choice(elig, size=k_s, replace=False)
                votes = []
                for w in panel:
                    if i >= 0 and coll[w] and coll[i]:
                        v = True
                    elif adap[w] and w_act[w] == 1:
                        v = True
                    else:
                        v = Q + rng.normal(0, P.sigma_obs) >= GOOD
                    votes.append((int(w), v))
                c["votes"] += k_s
                A = [w for w, v in votes if v]
                accepted = len(A) >= a_s
                q = float(np.mean(tau[A])) * len(A) / k_s if A else 0.0
            else:
                if hp:
                    continue
                votes, A, accepted, q = [], [], True, 1.0

            pen = (lambda w: P.phi * tau[w] / len(A)) if P.share_penalty \
                else (lambda w: P.phi * tau[w])
            rew = {w: 0.0 for w, _ in votes}
            pnl = {w: 0.0 for w, _ in votes}

            if hp:
                c["hp"] += 1
                c["hp_pass"] += accepted
                for w in A:
                    dNeg[w] += pen(w); pnl[w] += pen(w)
                if P.reward == "majority":
                    for w, v in votes:
                        if not v:
                            dR[w] += P.eta_w / k_s; rew[w] += P.eta_w / k_s
            elif not accepted:
                if not is_bad: c["good_rej"] += 1
                if P.reward == "majority":
                    for w, v in votes:
                        if not v:
                            dR[w] += P.eta_w / k_s; rew[w] += P.eta_w / k_s
            else:
                if forced_audit:
                    audited = True
                elif P.audit == "targeted":
                    audited = q < P.q_min and rng.random() < P.p_a
                else:
                    audited = rng.random() < P.p_a
                c["audits"] += audited
                verdict_bad = is_bad != (rng.random() < P.audit_err)
                if P.appeal and audited and verdict_bad and P.audit_err > 0:
                    c["audits"] += 1
                    verdict_bad = is_bad != (rng.random() < P.audit_err)
                sanctioned = audited and verdict_bad
                if sanctioned:
                    dS[i] += P.kappa_s
                    for w in A:
                        dNeg[w] += pen(w); pnl[w] += pen(w)
                    if P.reward == "majority":
                        for w, v in votes:
                            if not v:
                                dR[w] += P.eta_w / k_s; rew[w] += P.eta_w / k_s
                else:
                    if is_bad: c["bad_pass"] += 1
                    dG[i] += P.eta * q
                    active[i] = True
                    if P.reward == "approvers":
                        for w in A:
                            dR[w] += P.eta_w * q / len(A)
                            rew[w] += P.eta_w * q / len(A)
                    elif P.reward == "majority":
                        for w in A:
                            dR[w] += P.eta_w / k_s; rew[w] += P.eta_w / k_s
            for w, _ in votes:
                if adap[w]:
                    w_rec[w].append((int(w_act[w]), rew[w], pnl[w]))

        # la récompense de témoin ne compense pas l'absence de contribution
        dR = np.where(active, dR, 0.0)
        dD = np.where(active, 0.0, P.delta * tau)
        new = np.clip(tau + dG + dR - dNeg - dS - dD, 0, 1)

        for i in np.flatnonzero(adap):
            if a_act[i] >= 0:
                a = a_act[i]
                g_eff = min(dG[i], 1 - tau[i])
                pay = g_eff - dS[i] - dD[i] - (COST_H if a == 0 else 0.0)
                Qa[i, a] += lr * (pay - Qa[i, a])
            for wa in (0, 1):
                pays = [(r if active[i] else 0.0) - pn - (COST_V if wa == 0 else 0.0)
                        for (a_, r, pn) in w_rec[i] if a_ == wa]
                if pays:
                    Qw[i, wa] += lr * (np.mean(pays) - Qw[i, wa])
        if adap.any():
            chosen = a_act[adap]
            fraud_share.append(float(np.mean(chosen[chosen >= 0] == 1)) if (chosen >= 0).any() else np.nan)
            stamp_share.append(float(np.mean(w_act[adap] == 1)))
        tau = new
        hist[t + 1] = tau

    groups = {}
    for g in ("honest", "freerider", "colluder", "fraud", "adaptive"):
        m = beh == g
        if m.any():
            groups[g] = dict(final=float(tau[m].mean()), traj=hist[:, m].mean(1))
    return dict(groups=groups, counts=c, fraud=fraud_share, stamp=stamp_share,
                final_all=tau, k=k, a=a_req)


# ════════════════════════════════════════════════════════════════════
# Outils
# ════════════════════════════════════════════════════════════════════
def ci(x, B=2000):
    x = np.asarray(x, float)
    x = x[~np.isnan(x)]
    r = np.random.default_rng(0)
    boots = r.choice(x, size=(B, len(x)), replace=True).mean(axis=1)
    return [float(x.mean()), float(np.percentile(boots, 2.5)),
            float(np.percentile(boots, 97.5))]


def _job(args):
    return run(*args)


def batch(P, behaviors, pdef, seeds, periods=T):
    with Pool(os.cpu_count()) as pool:
        return pool.map(_job, [(P, behaviors, pdef, s, periods) for s in seeds])


def pop(n, f_coll=0.0, f_free=0.0, f_fraud=0.0):
    nc, nf, nx = round(n * f_coll), round(n * f_free), round(n * f_fraud)
    return ["honest"] * (n - nc - nf - nx) + ["freerider"] * nf + \
           ["fraud"] * nx + ["colluder"] * nc


def hyper_capture(m, c, k, a):
    return sum(math.comb(c, x) * math.comb(m - c, k - x)
               for x in range(a, min(c, k) + 1)) / math.comb(m, k)


def rates(results):
    bs = sum(r["counts"]["bad_sub"] for r in results)
    bp = sum(r["counts"]["bad_pass"] for r in results)
    gs = sum(r["counts"]["good_sub"] for r in results)
    gr = sum(r["counts"]["good_rej"] for r in results)
    return dict(fraude_passee=bp / max(bs, 1), faux_rejet=gr / max(gs, 1),
                votes_par_signal=sum(r["counts"]["votes"] for r in results) / max(bs + gs, 1),
                audits_par_signal=sum(r["counts"]["audits"] for r in results) / max(bs + gs, 1))


def group_ci(results, g):
    return ci([r["groups"][g]["final"] for r in results if g in r["groups"]])


# ════════════════════════════════════════════════════════════════════
# Expériences
# ════════════════════════════════════════════════════════════════════
def E1():
    """Tolérance au défaut : 20 honnêtes dont 5 défaillants à p_d."""
    out = {}
    for name, P in (("v2.0", V20), ("v2.1", V21)):
        rows = []
        for pd in np.round(np.arange(0, 0.41, 0.05), 2):
            res = batch(P, ["honest"] * 20, [0.0] * 15 + [float(pd)] * 5,
                        range(1000, 1200))
            rows.append([float(pd)] + ci([r["final_all"][15:].mean() for r in res]))
        out[name] = dict(rows=rows, kappa=P.kappa, eta=P.eta)
    return out


def E2():
    """Gain net d'une coalition (40 % ou 60 %) en fonction de p_a."""
    out = {}
    for name, P, fc in (("v2.0", V20, 0.4), ("v2.1", V21, 0.4), ("v2.1, 60 %", V21, 0.6)):
        rows = []
        for pa in np.round(np.arange(0, 0.51, 0.05), 2):
            res = batch(replace(P, p_a=float(pa)), pop(20, fc), [0.0] * 20,
                        range(2000, 2200))
            rows.append([float(pa)] + ci([r["groups"]["colluder"]["final"] - P.tau0
                                          for r in res]))
        out[name] = rows
    return out


def E3():
    """Capture du panel : taux d'acceptation des signaux colludeurs (1 période)."""
    out = {}
    n = 20
    for name, P in (("v2.0", V20), ("v2.1", V21)):
        P0 = replace(P, p_a=0.0, honeypot=0.0)
        rows = []
        for nc in range(2, 11):
            res = batch(P0, ["honest"] * (n - nc) + ["colluder"] * nc, [0.0] * n,
                        range(3000, 3100), periods=1)
            sub = sum(r["counts"]["bad_sub"] for r in res)
            acc = sum(r["counts"]["bad_pass"] for r in res)
            k = res[0]["k"]; a = res[0]["a"]
            rows.append([nc / n, acc / max(sub, 1), hyper_capture(n - 1, nc - 1, k, a)])
        out[name] = dict(k=k, a=a, rows=rows)
    return out


def E4():
    """Population mixte : 10 honnêtes, 4 passagers clandestins, 6 colludeurs."""
    beh = pop(20, 0.3, 0.2)
    pdef = [0.02 if b == "honest" else 0.0 for b in beh]
    out, traj = {}, {}
    for name, P in (("v1.1", V1), ("v2.0", V20), ("v2.1", V21)):
        res = batch(P, beh, pdef, range(4000, 4200))
        out[name] = {g: group_ci(res, g) for g in ("honest", "freerider", "colluder")}
        out[name].update(rates(res))
        traj[name] = {g: np.mean([r["groups"][g]["traj"] for r in res], axis=0).tolist()
                      for g in ("honest", "freerider", "colluder")}
    return out, traj


def E5():
    """Valeur des témoins : 13 honnêtes, 3 fraudeurs isolés, 4 colludeurs."""
    beh = pop(20, 0.2, 0.0, 0.15)
    pdef = [0.0] * 20
    out = {}
    for name, P in (("audit seul", AUDIT_SEUL), ("témoins sans responsabilité", SANS_RESP),
                    ("v2.1 complet", V21)):
        res = batch(P, beh, pdef, range(5000, 5200))
        out[name] = {g: group_ci(res, g) for g in ("honest", "fraud", "colluder")}
        out[name].update(rates(res))
    need = []
    for pa in (0.5, 0.8, 0.9, 0.95, 0.99):
        res = batch(replace(AUDIT_SEUL, p_a=pa), beh, pdef, range(5000, 5100))
        need.append([pa, rates(res)["fraude_passee"]])
    out["audit_seul_pa"] = need
    return out


def E6():
    """Agents adaptatifs : 20 membres qui apprennent à frauder et à tamponner."""
    out = {}
    for name, P in (("v1.1", V1), ("v2.0", V20), ("v2.1", V21),
                    ("v2.1 sans pièges", replace(V21, honeypot=0.0)),
                    ("v2.1 sans responsabilité", SANS_RESP)):
        res = batch(P, ["adaptive"] * 20, [0.0] * 20, range(6000, 6050), periods=300)
        F = np.array([r["fraud"] for r in res]); S = np.array([r["stamp"] for r in res])
        out[name] = dict(fraud=np.nanmean(F, 0).tolist(), stamp=np.nanmean(S, 0).tolist(),
                         fraud_end=ci(np.nanmean(F[:, -50:], 1)),
                         stamp_end=ci(np.nanmean(S[:, -50:], 1)),
                         **rates(res))
    return out


def E7():
    """Sensibilité de v2.1 (population proche de E4) — un facteur à la fois."""
    def cfg(P=V21, n=20, fc=0.3):
        beh = pop(n, fc, 0.1)
        return P, beh, [0.02 if b == "honest" else 0.0 for b in beh]
    variants = [("référence", cfg())]
    for v in (0.05, 0.20):
        variants.append((f"sigma_obs={v}", cfg(replace(V21, sigma_obs=v))))
    variants.append(("sigma_obs=0.2, theta=0.5", cfg(replace(V21, sigma_obs=0.2, theta=0.5))))
    for v in (0.05, 0.10):
        variants.append((f"erreur d'audit={v}", cfg(replace(V21, audit_err=v))))
        variants.append((f"erreur d'audit={v}, sans contre-audit",
                         cfg(replace(V21, audit_err=v, appeal=False))))
    for v in (0.3, 0.7):
        variants.append((f"tau0={v}", cfg(replace(V21, tau0=v))))
    for v in (10, 40):
        variants.append((f"n={v}", cfg(n=v)))
    variants.append(("n=10, panel fixe", cfg(replace(V21, adaptive_k=False), n=10)))
    for v in (0.1, 0.5):
        variants.append((f"coalition={int(v*100)}%", cfg(fc=v)))
    for v in (0.5, 1.0):
        variants.append((f"theta={v}", cfg(replace(V21, theta=v))))
    for v in (0.05, 0.30):
        variants.append((f"p_a={v}", cfg(replace(V21, p_a=v))))
    for v in (0.0, 0.10):
        variants.append((f"pièges={v}", cfg(replace(V21, honeypot=v))))
    out = {}
    for name, (P, beh, pdef) in variants:
        res = batch(P, beh, pdef, range(7000, 7100))
        row = {g: group_ci(res, g) for g in ("honest", "colluder")}
        row["gain_colludeurs"] = ci([r["groups"]["colluder"]["final"] - P.tau0 for r in res])
        row.update(rates(res))
        out[name] = row
    return out


# ════════════════════════════════════════════════════════════════════
# Figures (fr / en), tracées depuis resultats_v2.json
# ════════════════════════════════════════════════════════════════════
TXT = {
    "fr": dict(pd=r"probabilité de défaut par période $p_d$",
               final=r"score final moyen $\tau(T)$",
               pa=r"probabilité d'audit $p_a$",
               gain=r"gain net des colludeurs $\tau(T)-\tau_0$",
               coal="coalition", share=r"part de la coalition $c/n$",
               acc="taux d'acceptation\ndes signaux colludeurs",
               honest="honnêtes", freerider="passagers clandestins",
               colluder="colludeurs", rules="règles et paramètres",
               period="période", mean=r"score moyen $\tau$",
               fraud="part des auteurs qui fraudent",
               stamp="part des témoins qui tamponnent",
               nohp="v2.1 sans pièges", noacc="v2.1 sans responsabilité",
               fraud_acc="fraudes acceptées (%)", audit_only="audit seul",
               noacc_b="témoins sans resp.", full="v2.1 complet",
               fraudster="fraudeurs isolés", honest_final="score final des honnêtes",
               wrongrej="rejets à tort (%)", ref="référence"),
    "en": dict(pd=r"default probability per period $p_d$",
               final=r"mean final score $\tau(T)$",
               pa=r"audit probability $p_a$",
               gain=r"colluders' net gain $\tau(T)-\tau_0$",
               coal="coalition", share=r"coalition share $c/n$",
               acc="acceptance rate of\ncolluders' signals",
               honest="honest", freerider="free riders",
               colluder="colluders", rules="rules and parameters",
               period="period", mean=r"mean score $\tau$",
               fraud="share of authors who cheat",
               stamp="share of witnesses who rubber-stamp",
               nohp="v2.1 without decoys", noacc="v2.1 without accountability",
               fraud_acc="frauds accepted (%)", audit_only="audit only",
               noacc_b="no accountability", full="full v2.1",
               fraudster="isolated fraudsters", honest_final="honest members' final score",
               wrongrej="wrongful rejections (%)", ref="reference"),
}


def fig_E5(d, od, L, sfx):
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.4))
    ax = axes[0]
    pa = [0.15] + [r[0] for r in d["audit_seul_pa"]]
    fr = [d["audit seul"]["fraude_passee"]] + [r[1] for r in d["audit_seul_pa"]]
    ax.plot(pa, [100 * f for f in fr], "o-", color="C7", label=L["audit_only"])
    ax.plot([0.15], [100 * d["v2.1 complet"]["fraude_passee"]], "*", ms=14,
            color="C0", label=L["full"] + r" ($p_a=0{,}15$)")
    ax.set_xlabel(L["pa"]); ax.set_ylabel(L["fraud_acc"]); ax.set_yscale("log")
    ax.legend(fontsize=8); ax.grid(alpha=0.3, which="both")
    ax = axes[1]
    cfgs = [("audit seul", L["audit_only"]), ("témoins sans responsabilité", L["noacc_b"]),
            ("v2.1 complet", L["full"])]
    x = np.arange(3); w = 0.26
    for j, (g, col) in enumerate((("honest", "C2"), ("fraud", "C3"), ("colluder", "C1"))):
        m = [d[c][g][0] for c, _ in cfgs]
        lo = [d[c][g][0] - d[c][g][1] for c, _ in cfgs]
        hi = [d[c][g][2] - d[c][g][0] for c, _ in cfgs]
        lab = {"honest": L["honest"], "fraud": L["fraudster"], "colluder": L["colluder"]}[g]
        ax.bar(x + (j - 1) * w, m, w, yerr=[lo, hi], color=col, label=lab, capsize=2)
    ax.set_xticks(x); ax.set_xticklabels([l for _, l in cfgs], fontsize=8)
    ax.set_ylabel(L["final"]); ax.legend(fontsize=7); ax.grid(alpha=0.3, axis="y")
    fig.tight_layout(); fig.savefig(f"{od}/fig_E5_references{sfx}.pdf"); plt.close(fig)


E7_LABELS = {
    "fr": {"référence": "référence v2.1", "erreur d'audit": r"$\varepsilon_a$",
           "sans contre-audit": "sans contre-audit", "panel fixe": "panel non adaptatif",
           "pièges": "$h$", "coalition": "coalition"},
    "en": {"référence": "v2.1 reference", "erreur d'audit": r"$\varepsilon_a$",
           "sans contre-audit": "no counter-audit", "panel fixe": "non-adaptive panel",
           "pièges": "$h$", "coalition": "coalition"},
}


def e7_label(name, lang):
    T = E7_LABELS[lang]
    if name == "référence":
        return T["référence"]
    out = []
    for part in name.split(", "):
        if "=" in part:
            k, v = part.split("=")
            k = {"sigma_obs": r"$\sigma_{obs}$", "theta": r"$\theta$", "tau0": r"$\tau_0$",
                 "p_a": "$p_a$", "n": "$n$"}.get(k, T.get(k, k))
            out.append(f"{k} = {v}")
        else:
            out.append(T.get(part, part))
    return ", ".join(out)


def fig_E7(d, od, L, sfx):
    names = list(d.keys())
    y = np.arange(len(names))[::-1]
    fig, axes = plt.subplots(1, 2, figsize=(10, 6), sharey=True,
                             gridspec_kw=dict(width_ratios=[1.3, 1]))
    ax = axes[0]
    ref = d[names[0]]["honest"][0]
    for yi, nm in zip(y, names):
        m, lo, hi = d[nm]["honest"]
        col = "C3" if m < 0.8 else "C0"
        ax.errorbar(m, yi, xerr=[[m - lo], [hi - m]], fmt="o", color=col, capsize=2)
    ax.axvline(ref, color="gray", ls=":", lw=1)
    lang = "en" if sfx == "_en" else "fr"
    ax.set_yticks(y); ax.set_yticklabels([e7_label(n, lang) for n in names], fontsize=8)
    ax.set_xlabel(L["honest_final"]); ax.grid(alpha=0.3, axis="x")
    ax = axes[1]
    ax.barh(y + 0.2, [100 * d[n]["fraude_passee"] for n in names], 0.4, color="C1",
            label=L["fraud_acc"])
    ax.barh(y - 0.2, [100 * d[n]["faux_rejet"] for n in names], 0.4, color="C7",
            label=L["wrongrej"])
    ax.set_xlabel("%"); ax.legend(fontsize=8); ax.grid(alpha=0.3, axis="x")
    fig.tight_layout(); fig.savefig(f"{od}/fig_E7_sensibilite{sfx}.pdf"); plt.close(fig)


def fig_E1(d, od, L, sfx):
    fig, ax = plt.subplots(figsize=(6, 3.6))
    for (name, col) in (("v2.0", "C3"), ("v2.1", "C0")):
        rows = d[name]["rows"]
        x = [r[0] for r in rows]
        ax.plot(x, [r[1] for r in rows], "o-", color=col,
                label=rf"$\kappa={d[name]['kappa']}$, $\eta={d[name]['eta']}$")
        ax.fill_between(x, [r[2] for r in rows], [r[3] for r in rows], color=col, alpha=0.2)
        e = d[name]["eta"] * 0.91
        ax.axvline(e / (e + d[name]["kappa"]), color=col, ls="--", lw=1)
    ax.axhline(0.5, color="gray", lw=0.8, ls=":")
    ax.set_xlabel(L["pd"]); ax.set_ylabel(L["final"])
    ax.legend(); ax.grid(alpha=0.3); fig.tight_layout()
    fig.savefig(f"{od}/fig_E1_defaut{sfx}.pdf"); plt.close(fig)


def fig_E2(d, od, L, sfx):
    fig, ax = plt.subplots(figsize=(6, 3.6))
    labels = {"v2.0": f"v2.0, {L['coal']} 40 %", "v2.1": f"v2.1, {L['coal']} 40 %",
              "v2.1, 60 %": f"v2.1, {L['coal']} 60 %"}
    for name, col in (("v2.0", "C3"), ("v2.1", "C0"), ("v2.1, 60 %", "C4")):
        rows = d[name]; x = [r[0] for r in rows]
        ax.plot(x, [r[1] for r in rows], "s-", color=col, label=labels[name])
        ax.fill_between(x, [r[2] for r in rows], [r[3] for r in rows], color=col, alpha=0.2)
    ax.axhline(0, color="k", lw=0.8)
    ax.set_xlabel(L["pa"]); ax.set_ylabel(L["gain"])
    ax.legend(); ax.grid(alpha=0.3); fig.tight_layout()
    fig.savefig(f"{od}/fig_E2_collusion{sfx}.pdf"); plt.close(fig)


def fig_E3(d, od, L, sfx):
    fig, ax = plt.subplots(figsize=(6, 3.6))
    for name, col in (("v2.0", "C3"), ("v2.1", "C0")):
        rows = d[name]["rows"]; x = [r[0] for r in rows]
        ax.plot(x, [r[1] for r in rows], "o", color=col,
                label=f"simulation {name} ($k={d[name]['k']}$, $a_k={d[name]['a']}$)")
        ax.plot(x, [r[2] for r in rows], "-", color=col, lw=1)
    ax.set_xlabel(L["share"]); ax.set_ylabel(L["acc"])
    ax.legend(fontsize=8); ax.grid(alpha=0.3); fig.tight_layout()
    fig.savefig(f"{od}/fig_E3_capture{sfx}.pdf"); plt.close(fig)


def fig_E4(traj, od, L, sfx):
    fig, axes = plt.subplots(1, 3, figsize=(10, 3.4), sharey=True)
    cols = {"honest": "C2", "freerider": "C7", "colluder": "C1"}
    for ax, cfgname in zip(axes, ("v1.1", "v2.0", "v2.1")):
        for g in cols:
            ax.plot(traj[cfgname][g], color=cols[g], label=L[g])
        ax.set_title(f"{L['rules']} {cfgname}"); ax.set_xlabel(L["period"])
        ax.grid(alpha=0.3)
    axes[0].set_ylabel(L["mean"]); axes[2].legend(fontsize=8)
    fig.tight_layout(); fig.savefig(f"{od}/fig_E4_comparaison{sfx}.pdf"); plt.close(fig)


def fig_E6(d, od, L, sfx):
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.4), sharey=True)
    for name, col in (("v1.1", "C3"), ("v2.0", "C1"), ("v2.1", "C0"),
                      ("v2.1 sans pièges", "C9"), ("v2.1 sans responsabilité", "C4")):
        lab = {"v2.1 sans pièges": L["nohp"], "v2.1 sans responsabilité": L["noacc"]}.get(name, name)
        for ax, key in zip(axes, ("fraud", "stamp")):
            y = np.array(d[name][key])
            y = np.convolve(y, np.ones(10) / 10, mode="valid")
            ax.plot(y, color=col, label=lab)
    axes[0].set_title(L["fraud"]); axes[1].set_title(L["stamp"])
    for ax in axes:
        ax.set_xlabel(L["period"]); ax.grid(alpha=0.3); ax.set_ylim(-0.02, 1.02)
    axes[1].legend(fontsize=7)
    fig.tight_layout(); fig.savefig(f"{od}/fig_E6_adaptatifs{sfx}.pdf"); plt.close(fig)


def figures(results, od):
    for lang, sfx in (("fr", ""), ("en", "_en")):
        L = TXT[lang]
        for e in ("E1", "E2", "E3", "E5", "E6", "E7"):
            if e in results:
                globals()[f"fig_{e}"](results[e], od, L, sfx)
        if "E4_traj" in results:
            fig_E4(results["E4_traj"], od, L, sfx)


def main():
    default = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "article-v2.0", "figures")
    args = sys.argv[1:]
    modes = {"E1", "E2", "E3", "E4", "E5", "E6", "E7", "figures"}
    od = args.pop(0) if args and args[0] not in modes else default
    only = args or ["E1", "E2", "E3", "E4", "E5", "E6", "E7"]
    os.makedirs(od, exist_ok=True)
    plt.rcParams.update({"font.size": 10})
    path = f"{od}/resultats_v2.json"
    results = json.load(open(path)) if os.path.exists(path) else {}
    for e in only:
        if e == "figures":
            continue
        print(f"── {e}", flush=True)
        if e == "E4":
            r, results["E4_traj"] = E4()
        else:
            r = globals()[e]()
        results[e] = r
        with open(path, "w") as f:
            json.dump(results, f, indent=1)
        print(json.dumps(r, indent=1)[:3000], flush=True)
    figures(results, od)


if __name__ == "__main__":
    main()
