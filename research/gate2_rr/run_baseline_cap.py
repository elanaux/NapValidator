"""Gate 2 Step 3 — BASELINE arm on CAP: the §9 harness, unchanged, on ECG-derived 5 s HR.

Imports night_features / onset_times / cv_scores / spread and all constants from
research/bidsleep/leadtime_harness.py unchanged. The only new code is the loader:
CAP needs no per-night alignment offset (hypnogram and EDF share a clock;
Amendment 4), so m_best = 0 and rs = first retained epoch start.

Comparability stop (pre-registered): all-N3 logreg mean AUROC averaged over the
read-L values must fall in [0.53, 0.69]; outside -> STOP and discuss.
"""
from __future__ import annotations

import csv
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "bidsleep"))
from leadtime_harness import (  # noqa: E402  (unchanged harness)
    night_features, onset_times, cv_scores, spread,
    EPOCH_S, N3, UNKNOWN, L_READ, N_FOLDS, FEATURE_NAMES,
)

DERIVED = os.path.join(HERE, "cap_derived")
COMPAT_LO, COMPAT_HI = 0.53, 0.69


def usable_records():
    rows = list(csv.DictReader(open(os.path.join(HERE, "cap_ingest_qc.csv"))))
    return [(r["record"], float(r["fs"])) for r in rows if r["excluded"] == "False"]


def build_samples(records):
    """Mirror of leadtime_harness.build_samples with the CAP loader and m_best = 0."""
    subj, feats, stage, tau_next, tau_first = [], [], [], [], []
    for rec, _ in records:
        z = np.load(os.path.join(DERIVED, f"{rec}.npz"))
        t, bpm, labels, rs = z["hr_t"], z["hr_bpm"].astype(float), z["labels"], float(z["rs"])
        m_best = 0
        N = labels.size
        X, ok = night_features(t, bpm)
        k = np.floor((t - rs) / EPOCH_S).astype(np.int64) - m_best
        in_win = (k >= 0) & (k < N)
        valid = ok & in_win
        if not valid.any():
            continue
        valid_idx = np.flatnonzero(valid)
        st = labels[k[valid]]
        keep = st != UNKNOWN
        valid_idx, st = valid_idx[keep], st[keep]
        if valid_idx.size == 0:
            continue
        td = t[valid_idx]
        ons = onset_times(labels, rs, m_best)
        if ons.size:
            pos = np.searchsorted(ons, td, side="right")
            tn = np.where(pos < ons.size, ons[np.minimum(pos, ons.size - 1)] - td, np.inf)
            tn[pos >= ons.size] = np.inf
            first_on = ons[0]
        else:
            tn = np.full(td.size, np.inf)
            first_on = np.inf
        subj.append(np.full(valid_idx.size, rec))
        feats.append(X[valid_idx])
        stage.append(st)
        tau_next.append(tn)
        tau_first.append(first_on - td)
    return (np.concatenate(subj), np.vstack(feats), np.concatenate(stage),
            np.concatenate(tau_next), np.concatenate(tau_first))


def read(name, X, mask, tau, groups, clf):
    Xs, taus, grp = X[mask], tau[mask], groups[mask]
    per_fold = []   # [L][fold]
    print(f"\n  {name} — {clf}   ({mask.sum():,} decision points, {len(np.unique(grp))} subjects)")
    print(f"  {'L(s)':>5} {'prev%':>7} {'AUROC':>7} {'fold min..max':>16} {'AUPRC':>7}   per-fold")
    for L in L_READ:
        y = (taus <= float(L)).astype(int)
        au, ap = cv_scores(Xs, y, grp, clf)
        m, lo, _, hi, arr = spread(au)
        per_fold.append(arr)
        print(f"  {L:>5} {100*y.mean():>7.3f} {m:>7.3f} {lo:>7.3f}..{hi:<7.3f} {np.mean(ap):>7.3f}   "
              + " ".join(f"{a:.3f}" for a in arr))
    fold_avg = np.mean(np.vstack(per_fold), axis=0)   # per-fold AUROC averaged over read-L
    print(f"  avg over read-L: mean {fold_avg.mean():.3f}   per-fold "
          + " ".join(f"{a:.3f}" for a in fold_avg) + f"   (min {fold_avg.min():.3f})")
    return fold_avg


def run(records, tag):
    subj, X, stage, tn, tf = build_samples(records)
    print(f"\n{'='*100}\n{tag}: {X.shape[0]:,} decision points, {len(np.unique(subj))} subjects, "
          f"features {FEATURE_NAMES}\n{'='*100}")
    nonN3 = stage != N3
    first_mask = nonN3 & (tf > 0)
    out = {}
    for clf in ("logreg", "rf"):
        out[("all", clf)] = read("all-N3", X, nonN3, tn, subj, clf)
    for clf in ("logreg", "rf"):
        out[("first", clf)] = read("first-N3-only (informational)", X, first_mask, tf, subj, clf)
    y0 = (stage == N3).astype(int)
    au, ap = cv_scores(X, y0, subj, "logreg")
    print(f"\n  L=0 concurrent N3-vs-rest (EXCLUDED from read): logreg AUROC {np.mean(au):.3f} "
          f"({np.min(au):.3f}..{np.max(au):.3f})  prevalence {100*y0.mean():.1f}%")
    return out


def main():
    recs = usable_records()
    print(f"usable CAP records after beat-removal rule: {len(recs)} "
          f"(>=200 Hz: {sum(fs >= 200 for _, fs in recs)})")
    out = run(recs, "BASELINE — all usable subjects (primary)")
    m = out[("all", "logreg")].mean()
    print(f"\n{'#'*100}\nCOMPARABILITY STOP (pre-registered): all-N3 logreg avg-over-read-L = {m:.3f}; "
          f"window [{COMPAT_LO}, {COMPAT_HI}] -> "
          f"{'INSIDE — comparable' if COMPAT_LO <= m <= COMPAT_HI else 'OUTSIDE — STOP'}\n"
          f"BidSleep reference (§9): logreg 0.61 (0.612/0.615/0.610/0.607), per-fold ~0.55-0.67; RF 0.59-0.60\n{'#'*100}")
    if "--subset" in sys.argv:
        run([r for r in recs if r[1] >= 200], "BASELINE — >=200 Hz subset (informational)")


if __name__ == "__main__":
    main()
