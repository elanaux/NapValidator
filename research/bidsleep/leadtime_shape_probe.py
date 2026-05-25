"""Temporal-SHAPE feature probe (pre-registered) — §7 feature-expansion, STOP AT CURVE.

Diagnosis from the L-sweep: the 3 baseline features (sd_60, drop_vs_base,
slope_120) are all scalar collapses of HR *level* — they cannot see temporal
*shape*. This probe tests whether trajectory shape carries signal the scalars
miss. NOT K-selection, NOT the detector build.

PROTOCOL — identical to leadtime_harness.py (reused unchanged):
  subject-level GroupKFold(5); causal/trailing windows only; both label sets
  (first-N3-only, all-N3); L grid 15/30/60/90 s; L=0 computed but EXCLUDED from
  the read and flagged circularity-flattered. Metrics: held-out AUROC + per-fold
  min..max + AUPRC/prevalence. The ONLY protocol addition is leak-safe per-fold
  winsorisation of the curvature feature (clip bounds fit on TRAIN folds only),
  which the task explicitly sanctions; the 3 baseline features and AC1/reversal
  are clipped with fixed physiological/mathematical constants.

SHAPE FEATURES (causal, trailing W_SHAPE=120 s, added one at a time):
  ac1      — lag-1 autocorrelation of HR in the window  (persistence vs choppy); bound [-1,1]
  curv     — 2nd-order (quadratic) OLS coefficient, bpm/min^2 (is the descent curving);
             RAW here, winsorised to TRAIN-fold [0.5, 99.5] pct inside CV (no leak)
  revrate  — fraction of interior points that are local direction reversals (smooth vs jittery); bound [0,1]

PRE-REGISTERED PASS BAR (judged on all-N3 only; first-N3 is informational):
  passes iff mean AUROC >= 0.65 AND per-fold minimum >= 0.60 — BOTH.
  State the number against the bar; DO NOT declare a verdict.

Fair comparison: every feature set is evaluated on the SAME row set (samples
where ALL candidate features are finite), so incremental AUROC reflects the
feature, not a shifting sample population. Baseline is re-reported on this
common set; the bar's absolute thresholds (0.65 / 0.60) are unaffected.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from sklearn.linear_model import LogisticRegression
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import GroupKFold
from sklearn.metrics import roc_auc_score, average_precision_score

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_shape_hypothesis import rolling_sd_trailing  # noqa: E402
from verify_alignment import load_night  # noqa: E402
from leadtime_harness import (  # reuse exactly  # noqa: E402
    load_usable, night_features, onset_times, EPOCH_S, N3, UNKNOWN, RF_KW,
)

ROOT = os.path.dirname(os.path.abspath(__file__))
W_SHAPE = 120.0
WARMUP_S = 300.0
L_READ = [15, 30, 60, 90]
N_FOLDS = 5

# Feature layout in the pooled matrix
COLS = ["sd_60", "drop_vs_base", "slope_120", "ac1", "curv", "revrate"]
BASELINE = ["sd_60", "drop_vs_base", "slope_120"]
SHAPE = ["ac1", "curv", "revrate"]
SOFT_CLIP = {"curv"}                       # train-fold-winsorised; others use fixed constants
CURV_CLIP_PCT = (0.5, 99.5)


# ---------- shape features (causal, trailing W_SHAPE) ----------

def shape_features(t, bpm):
    """ac1 [-1,1], curv (bpm/min^2, RAW), revrate [0,1] over trailing W_SHAPE.
    Two-pointer trailing window; NaN where <6 samples or no time spread."""
    n = len(t)
    ac1 = np.full(n, np.nan)
    curv = np.full(n, np.nan)
    rev = np.full(n, np.nan)
    j = 0
    for i in range(n):
        while t[j] < t[i] - W_SHAPE:
            j += 1
        m = i - j + 1
        if m < 6:
            continue
        y = bpm[j:i + 1]
        x = t[j:i + 1] - t[i]            # centre at decision point (causal; <=0)
        if x[0] == x[-1]:
            continue
        d = y - y.mean()
        denom = float((d * d).sum())
        if denom > 0:
            ac1[i] = float((d[1:] * d[:-1]).sum() / denom)
        # quadratic OLS coefficient (bpm/s^2 -> bpm/min^2)
        try:
            c2 = np.polyfit(x, y, 2)[0]
            curv[i] = float(c2) * 3600.0
        except Exception:
            pass
        # direction reversals among consecutive diffs (ignore exact ties)
        dd = np.diff(y)
        s = np.sign(dd)
        s = s[s != 0]
        if s.size >= 2:
            rev[i] = float((s[1:] != s[:-1]).sum()) / (s.size - 1)
    ac1 = np.clip(ac1, -1.0, 1.0)
    rev = np.clip(rev, 0.0, 1.0)         # already in [0,1]; guard
    return np.column_stack([ac1, curv, rev])


def build_all():
    subj, feats, stage, tau_next, tau_first = [], [], [], [], []
    for s, night, m_best in load_usable():
        t, bpm, labels, rs, _ = load_night(s, night)
        N = labels.size
        Xb, okb = night_features(t, bpm)          # sd_60, drop_vs_base, slope_120 (clipped)
        Xs = shape_features(t, bpm)               # ac1, curv(raw), revrate
        tt = t - t[0]
        k = np.floor((t - rs) / EPOCH_S).astype(np.int64) - m_best
        in_win = (k >= 0) & (k < N)
        X6 = np.column_stack([Xb, Xs])
        ok = okb & in_win & (tt >= WARMUP_S) & np.isfinite(X6).all(axis=1)
        if not ok.any():
            continue
        vi = np.flatnonzero(ok)
        st = labels[k[vi]]
        keep = st != UNKNOWN
        vi, st = vi[keep], st[keep]
        if vi.size == 0:
            continue
        td = t[vi]
        ons = onset_times(labels, rs, m_best)
        if ons.size:
            pos = np.searchsorted(ons, td, side="right")
            tn = np.where(pos < ons.size, ons[np.minimum(pos, ons.size - 1)] - td, np.inf)
            tn[pos >= ons.size] = np.inf
            first_on = ons[0]
        else:
            tn = np.full(td.size, np.inf)
            first_on = np.inf
        subj.append(np.full(vi.size, s))
        feats.append(X6[vi])
        stage.append(st)
        tau_next.append(tn)
        tau_first.append(first_on - td)
    return (np.concatenate(subj), np.vstack(feats), np.concatenate(stage),
            np.concatenate(tau_next), np.concatenate(tau_first))


# ---------- CV (identical protocol + leak-safe per-fold winsorisation) ----------

def cv_eval(X, y, groups, soft_idx, clf_kind):
    gkf = GroupKFold(n_splits=N_FOLDS)
    aurocs, auprcs = [], []
    for tr, te in gkf.split(X, y, groups):
        if y[tr].sum() == 0 or y[te].sum() == 0:
            continue
        Xtr, Xte = X[tr].copy(), X[te].copy()
        for c in soft_idx:                         # winsorise soft cols on TRAIN only
            lo, hi = np.percentile(Xtr[:, c], CURV_CLIP_PCT)
            Xtr[:, c] = np.clip(Xtr[:, c], lo, hi)
            Xte[:, c] = np.clip(Xte[:, c], lo, hi)
        if clf_kind == "logreg":
            sc = StandardScaler().fit(Xtr)
            clf = LogisticRegression(max_iter=2000, class_weight="balanced")
            clf.fit(sc.transform(Xtr), y[tr])
            p = clf.predict_proba(sc.transform(Xte))[:, 1]
        else:
            clf = RandomForestClassifier(class_weight="balanced_subsample", **RF_KW)
            clf.fit(Xtr, y[tr])
            p = clf.predict_proba(Xte)[:, 1]
        aurocs.append(roc_auc_score(y[te], p))
        auprcs.append(average_precision_score(y[te], p))
    return aurocs, auprcs


def evaluate_set(X, cols_idx, soft_idx, mask, tau, groups, label_kind, clf_kind="logreg"):
    """Return per-L dict: {L: (mean, fmin, fmax, auprc, prev, folds)} for one feature set."""
    Xs = X[np.ix_(mask, cols_idx)]
    # remap soft indices into the sliced column space
    soft_local = [cols_idx.index(c) for c in soft_idx if c in cols_idx]
    taus, grp = tau[mask], groups[mask]
    out = {}
    for L in L_READ:
        y = (taus <= float(L)).astype(int)
        au, ap = cv_eval(Xs, y, grp, soft_local, clf_kind)
        if not au:
            out[L] = None
            continue
        a = np.array(au)
        out[L] = (float(a.mean()), float(a.min()), float(a.max()),
                  float(np.mean(ap)), 100.0 * float(y.mean()), a)
    return out


def summary_score(perL):
    """avg over read-L of (fold-mean, fold-min) — drives greedy selection."""
    means = [v[0] for v in perL.values() if v]
    mins = [v[1] for v in perL.values() if v]
    return (float(np.mean(means)) if means else np.nan,
            float(np.mean(mins)) if mins else np.nan)


def print_perL(title, perL):
    print(f"\n  {title}")
    print(f"  {'L(s)':>5} {'prev%':>7} {'AUROC':>7} {'fold min..max':>16} {'AUPRC':>7}")
    for L in L_READ:
        v = perL[L]
        if not v:
            print(f"  {L:>5}   (no positive test fold)")
            continue
        m, lo, hi, ap, prev, _ = v
        print(f"  {L:>5} {prev:>7.3f} {m:>7.3f} {lo:>7.3f}..{hi:<7.3f} {ap:>7.3f}")


def ci(name):  # column index
    return COLS.index(name)


def main():
    print("Building pooled baseline+shape feature table (common row set)...")
    subj, X, stage, tn, tf = build_all()
    print(f"  {X.shape[0]:,} decision points, {len(np.unique(subj))} subjects, cols={COLS}")
    nonN3 = stage != N3
    first_mask = nonN3 & (tf > 0)

    label_sets = {"all-N3": (nonN3, tn), "first-N3-only": (first_mask, tf)}

    # ---- forward selection driven by all-N3 (the gate) ----
    print(f"\n{'#'*100}\nFORWARD SELECTION (greedy, driven by all-N3 logreg; first-N3 reported alongside)\n{'#'*100}")
    nonN3_mask, tau_all = label_sets["all-N3"]

    def eval_cols(cols, kind="all-N3", clf="logreg"):
        mask, tau = label_sets[kind]
        soft = [c for c in SOFT_CLIP if c in cols]
        return evaluate_set(X, [ci(c) for c in cols], soft, mask, tau, subj, kind, clf)

    base_perL = eval_cols(BASELINE)
    base_mean, base_min = summary_score(base_perL)
    print_perL(f"BASELINE {BASELINE}  (avg-AUROC={base_mean:.3f}, avg-fold-min={base_min:.3f})", base_perL)

    # marginal contribution of each shape feature alone on top of baseline
    print(f"\n  -- marginal contribution of each shape feature (baseline + one) --")
    marg = {}
    for f in SHAPE:
        perL = eval_cols(BASELINE + [f])
        m, mn = summary_score(perL)
        marg[f] = (perL, m, mn)
        print(f"    +{f:9s}  avg-AUROC={m:.3f} (Δ{m-base_mean:+.3f})   avg-fold-min={mn:.3f} (Δ{mn-base_min:+.3f})")

    # greedy build-up
    KEEP_DMEAN = 0.003     # min avg-AUROC gain to keep
    FLOOR_TOL = 0.005      # avg-fold-min may not drop more than this
    kept = list(BASELINE)
    remaining = list(SHAPE)
    cur_mean, cur_min = base_mean, base_min
    history = []
    while remaining:
        best = None
        for f in remaining:
            perL = eval_cols(kept + [f])
            m, mn = summary_score(perL)
            if best is None or m > best[1]:
                best = (f, m, mn, perL)
        f, m, mn, perL = best
        if (m - cur_mean) >= KEEP_DMEAN and (mn - cur_min) >= -FLOOR_TOL:
            kept.append(f)
            remaining.remove(f)
            history.append((f, m - cur_mean, mn - cur_min, m, mn))
            print(f"  KEEP +{f}: avg-AUROC {cur_mean:.3f}->{m:.3f} (Δ{m-cur_mean:+.3f}), "
                  f"avg-fold-min {cur_min:.3f}->{mn:.3f} (Δ{mn-cur_min:+.3f})")
            cur_mean, cur_min = m, mn
        else:
            print(f"  STOP: best remaining +{f} gives avg-AUROC {m:.3f} (Δ{m-cur_mean:+.3f}), "
                  f"avg-fold-min {mn:.3f} (Δ{mn-cur_min:+.3f}) — fails keep rule "
                  f"(need ΔAUROC>={KEEP_DMEAN}, Δfloor>=-{FLOOR_TOL}).")
            break
    print(f"\n  KEPT FEATURE SET: {kept}")

    # ---- full read for baseline and final-kept, both label sets, logreg + RF ----
    results = {}
    for kind in ("all-N3", "first-N3-only"):
        print(f"\n{'='*100}\nLABEL SET: {kind}\n{'='*100}")
        b = eval_cols(BASELINE, kind)
        f_lr = eval_cols(kept, kind)
        f_rf = eval_cols(kept, kind, clf="rf")
        print_perL(f"baseline {BASELINE} (logreg)", b)
        print_perL(f"final {kept} (logreg)", f_lr)
        print_perL(f"final {kept} (RF — nonlinear ceiling)", f_rf)
        results[kind] = (b, f_lr, f_rf)

    # ---- L=0 state classifier (EXCLUDED, flattered) ----
    print(f"\n{'='*100}\nL=0 CONCURRENT STATE CLASSIFIER (annotated, EXCLUDED, circularity-flattered)\n{'='*100}")
    y0 = (stage == N3).astype(int)
    for tag, cols in (("baseline", BASELINE), ("final", kept)):
        soft = [c for c in SOFT_CLIP if c in cols]
        au, ap = cv_eval(X[:, [ci(c) for c in cols]], y0, subj, [cols.index(c) for c in soft], "logreg")
        a = np.array(au)
        print(f"  {tag:8s} {cols}: AUROC {a.mean():.3f} ({a.min():.3f}..{a.max():.3f})  AUPRC {np.mean(ap):.3f}")

    # ---- PASS BAR (all-N3 final, logreg) ----
    fin = results["all-N3"][1]
    fmean, fmin = summary_score(fin)
    # also report worst single read-L (bar is about the read points)
    perL_means = {L: fin[L][0] for L in L_READ if fin[L]}
    perL_mins = {L: fin[L][1] for L in L_READ if fin[L]}
    print(f"\n{'#'*100}\nPRE-REGISTERED PASS BAR  (all-N3, logreg, final set {kept})\n{'#'*100}")
    print(f"  Bar: mean AUROC >= 0.650 AND per-fold minimum >= 0.600  (BOTH)")
    print(f"  avg over read-L:  mean AUROC = {fmean:.3f}   per-fold-min = {fmin:.3f}")
    print(f"  per read-L mean AUROC: " + "  ".join(f"L{L}={perL_means[L]:.3f}" for L in perL_means))
    print(f"  per read-L fold-min :  " + "  ".join(f"L{L}={perL_mins[L]:.3f}" for L in perL_mins))
    cond_mean = fmean >= 0.650
    cond_min = fmin >= 0.600
    print(f"  condition mean>=0.65: {'MET' if cond_mean else 'NOT MET'} ({fmean:.3f})")
    print(f"  condition min>=0.60 : {'MET' if cond_min else 'NOT MET'} ({fmin:.3f})")
    print(f"  -> number-against-bar reported. VERDICT RESERVED FOR USER (not declared here).")

    # ---- plot baseline vs final, both label sets ----
    for kind in ("all-N3", "first-N3-only"):
        b, f_lr, f_rf = results[kind]
        fig, ax = plt.subplots(figsize=(8.5, 5.2))
        for perL, col, lab, mk in ((b, "C0", f"baseline {BASELINE}", "o"),
                                    (f_lr, "C2", f"final {kept} (logreg)", "s"),
                                    (f_rf, "C1", f"final {kept} (RF)", "^")):
            Ls = [L for L in L_READ if perL[L]]
            ax.plot(Ls, [perL[L][0] for L in Ls], "-" + mk, color=col, label=lab, lw=2)
            for L in Ls:
                ax.scatter([L] * len(perL[L][5]), perL[L][5], color=col, s=10, alpha=0.5)
        if kind == "all-N3":
            ax.axhline(0.65, color="r", ls="--", lw=1, label="pass-bar mean (0.65)")
            ax.axhline(0.60, color="r", ls=":", lw=1, label="pass-bar fold-min (0.60)")
        ax.axhline(0.5, color="k", ls=":", lw=0.8)
        ax.set_xlabel("lead time L (s)"); ax.set_ylabel("held-out AUROC (cross-subject)")
        ax.set_title(f"Shape-feature probe — {kind}")
        ax.set_ylim(0.45, 0.85); ax.grid(alpha=0.3); ax.legend(fontsize=7.5)
        fig.tight_layout()
        fn = f"{ROOT}/shape_probe_{kind.replace('-', '_')}.png"
        fig.savefig(fn, dpi=130)
        print(f"  wrote {fn}")

    print("\nDONE — curves + reads + bar number above. No K, no detector (by request).")


if __name__ == "__main__":
    main()
