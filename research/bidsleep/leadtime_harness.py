"""Lead-time Deep-onset detector — LEARNABILITY harness (§7 steps 4-5).

STOPS AT THE CURVE, by request: no K selection, no shippable detector.
For EACH onset definition (first-N3-only and all-N3) separately, produces:
  - the learnability curve: held-out AUROC vs lead time L, with PER-FOLD spread
    (the 5 fold values, not just the mean — 45 subjects / ~100 test onsets per
    fold is noisy and a mean would over-read);
  - the feasibility READ at rouse latencies L = 15 / 30 / 60 / 90 s
    (AUROC mean + per-fold min..max, AUPRC, positive prevalence; logreg & RF);
  - an L=0 point computed as a CONCURRENT STATE CLASSIFIER, annotated
    circularity-flattered (Gate-A alignment was tuned to maximise the same
    rolling-HR-SD signal the model uses) and EXCLUDED from the read.

CAUSALITY (enforced train AND eval): every feature is a TRAILING (backward-only)
window ending at the decision sample. Decision points are HR sample times
(median ~5 s) so L=15 s is resolvable.

CV: subject-level GroupKFold(5) — train on some subjects, test on DIFFERENT
subjects (cross-subject aggregate, the real product requirement). Standardiser
fit on train only.

Corpus: the confidently-aligned usable nights from alignment_table.csv
(sweep_alignment.py), each shifted by its per-night best-fit offset.
"""
from __future__ import annotations

import csv
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

ROOT = os.path.dirname(os.path.abspath(__file__))
EPOCH_S = 30.0
N3 = 3
UNKNOWN = 5

# Feature windows (trailing, seconds)
W_SD = 60.0
W_SHORT = 60.0
W_BASE = 300.0
W_SLOPE = 120.0
WARMUP_S = 300.0          # require 300 s of preceding HR before a sample is a decision point
FEATURE_NAMES = ["sd_60", "drop_vs_base", "slope_120"]  # variability / level-relative / shape

# Sweep + read points
L_SWEEP = [15, 30, 45, 60, 75, 90, 120, 150, 180, 240]
L_READ = [15, 30, 60, 90]
N_FOLDS = 5
RF_KW = dict(n_estimators=200, max_depth=12, min_samples_leaf=50, n_jobs=-1, random_state=0)


# ---------- trailing (causal) features ----------

def _trailing_sums(x, lo, hi_excl):
    """cumulative-sum windowed total for window [lo[i], i] inclusive."""
    c = np.concatenate([[0.0], np.cumsum(x)])
    return c[hi_excl] - c[lo]


def night_features(t, bpm):
    """Return (X[n,3], ok[n]) with strictly-trailing windows. ok marks samples
    whose every feature window has enough samples."""
    n = len(t)
    tt = t - t[0]
    idx_all = np.arange(n)
    hi = idx_all + 1

    def win_lo(w):
        return np.searchsorted(tt, tt - w, side="left")

    # short & base means -> drop
    lo_s, lo_b = win_lo(W_SHORT), win_lo(W_BASE)
    cnt_s, cnt_b = idx_all - lo_s + 1, idx_all - lo_b + 1
    sum_s = _trailing_sums(bpm, lo_s, hi)
    sum_b = _trailing_sums(bpm, lo_b, hi)
    mean_s = np.where(cnt_s >= 3, sum_s / np.maximum(cnt_s, 1), np.nan)
    mean_b = np.where(cnt_b >= 5, sum_b / np.maximum(cnt_b, 1), np.nan)
    drop = mean_s - mean_b   # < 0 when HR has fallen below its recent baseline

    # trailing OLS slope over W_SLOPE, in bpm/min
    lo_p = win_lo(W_SLOPE)
    cnt_p = idx_all - lo_p + 1
    Sx = _trailing_sums(tt, lo_p, hi)
    Sxx = _trailing_sums(tt * tt, lo_p, hi)
    Sy = _trailing_sums(bpm, lo_p, hi)
    Sxy = _trailing_sums(tt * bpm, lo_p, hi)
    denom = cnt_p * Sxx - Sx * Sx
    span_p = tt - tt[lo_p]                       # real time spread in the slope window
    with np.errstate(divide="ignore", invalid="ignore"):
        slope = np.where((cnt_p >= 4) & (denom > 0) & (span_p >= 0.5 * W_SLOPE),
                         (cnt_p * Sxy - Sx * Sy) / denom * 60.0, np.nan)

    # trailing SD (reuse canonical definition)
    sd = rolling_sd_trailing(t, bpm, W_SD)

    X = np.column_stack([sd, drop, slope])
    ok = np.isfinite(X).all(axis=1) & (tt >= WARMUP_S)
    # clip to physiological bounds (kills tiny-denominator OLS slope artifacts that
    # otherwise overflow the linear model); HR rarely moves faster than ~40 bpm/min.
    X[:, 0] = np.clip(X[:, 0], 0.0, 30.0)        # sd_60
    X[:, 1] = np.clip(X[:, 1], -40.0, 40.0)      # drop_vs_base
    X[:, 2] = np.clip(X[:, 2], -40.0, 40.0)      # slope_120
    return X, ok


def onset_times(labels, rs, m_best):
    """HR-time of each N3 onset (first N3 epoch after a non-N3 epoch)."""
    is_n3 = labels == N3
    onset_eps = np.flatnonzero(np.concatenate([[False], is_n3[1:] & ~is_n3[:-1]]))
    return rs + (onset_eps + m_best) * EPOCH_S   # epoch e starts at this HR time


# ---------- build the pooled sample table ----------

def load_usable():
    rows = []
    with open(f"{ROOT}/alignment_table.csv") as f:
        for r in csv.DictReader(f):
            if r["usable"] == "True":
                rows.append((r["subject"], r["night"], int(round(float(r["best_off_s"]) / EPOCH_S))))
    return rows


def build_samples():
    subj, feats, stage, tau_next, tau_first = [], [], [], [], []
    for s, night, m_best in load_usable():
        t, bpm, labels, rs, _ = load_night(s, night)
        N = labels.size
        X, ok = night_features(t, bpm)
        k = np.floor((t - rs) / EPOCH_S).astype(np.int64) - m_best
        in_win = (k >= 0) & (k < N)
        valid = ok & in_win
        if not valid.any():
            continue
        kk = k[valid]
        st = labels[kk]
        valid_idx = np.flatnonzero(valid)
        # drop Unknown-labelled epochs
        keep = st != UNKNOWN
        valid_idx, st = valid_idx[keep], st[keep]
        if valid_idx.size == 0:
            continue
        td = t[valid_idx]

        ons = onset_times(labels, rs, m_best)
        if ons.size:
            # next onset strictly after t_d
            pos = np.searchsorted(ons, td, side="right")
            tn = np.where(pos < ons.size, ons[np.minimum(pos, ons.size - 1)] - td, np.inf)
            tn[pos >= ons.size] = np.inf
            first_on = ons[0]
        else:
            tn = np.full(td.size, np.inf)
            first_on = np.inf
        tf = first_on - td   # >0 before first onset, <=0 after (or inf if no onset)

        subj.append(np.full(valid_idx.size, s))
        feats.append(X[valid_idx])
        stage.append(st)
        tau_next.append(tn)
        tau_first.append(tf)

    return (np.concatenate(subj), np.vstack(feats), np.concatenate(stage),
            np.concatenate(tau_next), np.concatenate(tau_first))


# ---------- CV ----------

def cv_scores(X, y, groups, clf_kind):
    """Per-fold (auroc, auprc) on held-out subjects. Returns lists (len<=N_FOLDS)."""
    gkf = GroupKFold(n_splits=N_FOLDS)
    aurocs, auprcs = [], []
    for tr, te in gkf.split(X, y, groups):
        if y[tr].sum() == 0 or y[te].sum() == 0:
            continue  # fold has no positives -> metric undefined
        if clf_kind == "logreg":
            sc = StandardScaler().fit(X[tr])
            clf = LogisticRegression(max_iter=2000, class_weight="balanced")
            clf.fit(sc.transform(X[tr]), y[tr])
            p = clf.predict_proba(sc.transform(X[te]))[:, 1]
        else:
            clf = RandomForestClassifier(class_weight="balanced_subsample", **RF_KW)
            clf.fit(X[tr], y[tr])
            p = clf.predict_proba(X[te])[:, 1]
        aurocs.append(roc_auc_score(y[te], p))
        auprcs.append(average_precision_score(y[te], p))
    return aurocs, auprcs


def spread(vals):
    a = np.array(vals, float)
    return (float(np.mean(a)), float(np.min(a)), float(np.median(a)), float(np.max(a)), a)


# ---------- run one onset definition ----------

def run_onset_def(name, X, mask, tau, groups, want_rf_at):
    """Sweep L over the lead-time curve for this onset definition."""
    Xs, taus, grp = X[mask], tau[mask], groups[mask]
    n = Xs.shape[0]
    print(f"\n{'='*100}\nONSET DEFINITION: {name}   ({n:,} decision points, "
          f"{len(np.unique(grp))} subjects)\n{'='*100}")
    print(f"{'L(s)':>5} {'prev%':>7} {'AUROC mean':>11} {'fold min..max':>16} "
          f"{'AUPRC':>7} {'(read)':>7}")
    curve = []
    for L in L_SWEEP:
        y = (taus <= float(L)).astype(int)
        prev = 100.0 * y.mean()
        au, ap = cv_scores(Xs, y, grp, "logreg")
        if not au:
            print(f"{L:>5} {prev:>7.3f}   (no positive test fold)")
            continue
        m, lo, md, hi, arr = spread(au)
        apm = float(np.mean(ap))
        tag = "READ" if L in L_READ else ""
        print(f"{L:>5} {prev:>7.3f} {m:>11.3f} {lo:>7.3f}..{hi:<7.3f} {apm:>7.3f} {tag:>7}")
        curve.append((L, m, lo, md, hi, arr, apm, prev))

    # RF at requested read points (nonlinear ceiling)
    print(f"\n  Random-forest at read points (nonlinear ceiling):")
    rf_rows = []
    for L in want_rf_at:
        y = (taus <= float(L)).astype(int)
        au, ap = cv_scores(Xs, y, grp, "rf")
        if not au:
            continue
        m, lo, md, hi, arr = spread(au)
        print(f"    L={L:>3}s  AUROC {m:.3f}  ({lo:.3f}..{hi:.3f})   AUPRC {np.mean(ap):.3f}")
        rf_rows.append((L, m, lo, hi))
    return curve, rf_rows


def state_classifier_L0(X, stage, groups):
    """L=0 reference = concurrent N3-vs-rest. Circularity-flattered, EXCLUDED."""
    y = (stage == N3).astype(int)
    au_lr, ap_lr = cv_scores(X, y, groups, "logreg")
    au_rf, ap_rf = cv_scores(X, y, groups, "rf")
    print(f"\n{'='*100}\nL=0  CONCURRENT STATE CLASSIFIER  (annotated, EXCLUDED from read)\n{'='*100}")
    print(f"  ** circularity-flattered: Gate-A alignment maximised the same rolling-HR-SD "
          f"signal\n     this model uses, so this point is optimistic and is NOT part of the "
          f"feasibility read. **")
    if au_lr:
        m, lo, _, hi, _ = spread(au_lr)
        print(f"  logreg AUROC {m:.3f}  ({lo:.3f}..{hi:.3f})   AUPRC {np.mean(ap_lr):.3f}   "
              f"prevalence {100*y.mean():.1f}%")
    if au_rf:
        m, lo, _, hi, _ = spread(au_rf)
        print(f"  RF     AUROC {m:.3f}  ({lo:.3f}..{hi:.3f})   AUPRC {np.mean(ap_rf):.3f}")
    return (spread(au_lr)[0] if au_lr else np.nan)


def plot_curve(name, curve, rf_rows, l0_auroc, fname):
    fig, ax = plt.subplots(figsize=(9, 5.5))
    Ls = [c[0] for c in curve]
    means = [c[1] for c in curve]
    # per-fold spread: scatter every fold value
    for c in curve:
        L, _, _, _, _, arr, _, _ = c
        ax.scatter([L] * len(arr), arr, color="#888", s=14, zorder=2,
                   label="per-fold" if c is curve[0] else None)
    ax.plot(Ls, means, "-o", color="C0", lw=2, zorder=3, label="logreg fold-mean AUROC")
    if rf_rows:
        ax.plot([r[0] for r in rf_rows], [r[1] for r in rf_rows], "--s",
                color="C1", lw=1.5, zorder=3, label="RF fold-mean AUROC")
    if np.isfinite(l0_auroc):
        ax.scatter([0], [l0_auroc], marker="*", s=260, color="C3", zorder=4,
                   label=f"L=0 state classifier (flattered, excluded): {l0_auroc:.2f}")
    ax.axhline(0.5, color="k", ls=":", lw=1, label="chance (AUROC=0.5)")
    for L in L_READ:
        ax.axvline(L, color="#cfe", lw=8, zorder=0)
    ax.set_xlabel("lead time L (s)  —  fire this far before N3 onset")
    ax.set_ylabel("held-out AUROC (cross-subject)")
    ax.set_title(f"Lead-time learnability — {name}\n(shaded bands = rouse-latency read points 15/30/60/90 s)")
    ax.set_ylim(0.45, 1.0)
    ax.legend(fontsize=8, loc="upper right")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(fname, dpi=130)
    print(f"  wrote {fname}")


def main():
    print("Building pooled causal-feature sample table from usable nights...")
    subj, X, stage, tau_next, tau_first = build_samples()
    print(f"  {X.shape[0]:,} valid decision points, {len(np.unique(subj))} subjects, "
          f"features = {FEATURE_NAMES}")

    l0 = state_classifier_L0(X, stage, subj)

    # all-N3: every non-N3 decision point; positive iff next onset within L
    nonN3 = stage != N3
    cA, rfA = run_onset_def("all-N3 (every descent)", X, nonN3, tau_next, subj, L_READ)
    plot_curve("all-N3 (every descent)", cA, rfA, l0, f"{ROOT}/learnability_all_n3.png")

    # first-N3-only: non-N3 points BEFORE the first onset; positive iff within L of it
    first_mask = nonN3 & (tau_first > 0)
    cB, rfB = run_onset_def("first-N3-only (first descent)", X, first_mask, tau_first, subj, L_READ)
    plot_curve("first-N3-only (first descent)", cB, rfB, l0, f"{ROOT}/learnability_first_n3.png")

    print("\nDONE — curves + reads above. K NOT selected, detector NOT built (by request).")


if __name__ == "__main__":
    main()
