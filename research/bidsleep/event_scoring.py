"""Per-nap event-scoring feasibility SURFACE — final modeling pass. STOP AT THE SURFACE.

Operationalises the lead-time score into a fire-once firing policy and scores the
PER-NAP product metric (deferred by every prior probe). No shippable detector,
no single operating point selected. The read is the user's.

REUSED UNCHANGED: aligned BidSleep corpus (locked per-night offsets), subject-level
GroupKFold(5), the 3 locked causal features (sd_60, drop_vs_base, slope_120),
logreg primary + RF cross-check.

"NAP" = one night recording (BidSleep is overnight; each usable night is one
fire-once event). Scored against the FIRST N3 onset of that night.

SCORE: one per-sample logreg P(Deep-approaching) from the 3 features, trained on the
ALL-N3 lead-time label at L_TRAIN=300 s (positive iff next N3 onset within 300 s).
300 s = middle of the early grid; ranking is ~L-insensitive (AUROC flat L=15..240).
Training decision points = non-N3 samples; at test the model is applied to EVERY
valid sample to form a causal score series.

FIRING POLICY (causal, held-out only): fire the first sample whose score stayed >= T
for >= S s, then the nap ends. Sustain = trailing-S-window min >= T with TOL_SUSTAIN=10 s
coverage tolerance; S=0 => fire on first sample >= T.

THRESHOLD T (LEAK GUARD): a nap false-fires at T iff it has a sustained crossing in the
"too-early" region (before onset-early; whole night for no-N3 naps). The largest such T
is the nap's value v. FF-rate(T)=frac(train v >= T), so T* for budget b = the (1-b)
quantile of TRAIN-nap v's. T depends on (S, early, budget); never on test.

The fire-time-vs-T step function per nap is recovered from the strictly-increasing
RECORD-highs of the sustained score (value,time) pairs: for threshold T the first
crossing is the earliest record whose value >= T. Precomputed once per nap.

ACCEPTANCE (LOCKED 3x4): HIT iff onset-early <= fire <= onset+late.
  early in {180,300,420}s; late in {0,30,60,120}s.
OUTCOMES (fire-once): no-N3 nap: fire=>FALSE-FIRE else CORRECT. N3 nap: none=>NO-FIRE-MISS;
  fire<onset-early=>EARLY-FALSE-FIRE; <=onset+late=>HIT; else=>LATE-FIRE (overshot Deep).
SCORABLE: no-N3 naps with a series; N3 naps with >=300 s pre-first-onset series.
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from verify_alignment import load_night  # noqa: E402
from leadtime_harness import load_usable, night_features, onset_times, EPOCH_S, N3, UNKNOWN, RF_KW  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
L_TRAIN = 300.0
EARLY = [180.0, 300.0, 420.0]
LATE = [0.0, 30.0, 60.0, 120.0]
SUSTAIN = [0.0, 30.0, 60.0]
BUDGETS = [0.10, 0.20, 0.30]
TOL_SUSTAIN = 10.0
PRE_ONSET_MIN = 300.0
N_FOLDS = 5
T_GRID = np.linspace(0.0, 1.0, 101)


# ---------- per-night records ----------

def build_nights():
    nights = []
    for s, night, m_best in load_usable():
        t, bpm, labels, rs, _ = load_night(s, night)
        N = labels.size
        X, ok = night_features(t, bpm)
        k = np.floor((t - rs) / EPOCH_S).astype(np.int64) - m_best
        valid = ok & (k >= 0) & (k < N)
        if not valid.any():
            continue
        kk = k[valid]
        st = labels[kk]
        keep = st != UNKNOWN
        vi = np.flatnonzero(valid)[keep]
        st = st[keep]
        if vi.size == 0:
            continue
        td = t[vi]
        ons = onset_times(labels, rs, m_best)
        first_onset = float(ons[0]) if ons.size else np.inf
        nights.append({"subj": s, "night": night, "t": td, "X": X[vi], "stage": st,
                       "first_onset": first_onset, "ons": ons})
    return nights


def tau_all(nap):
    ons, td = nap["ons"], nap["t"]
    if ons.size == 0:
        return np.full(td.size, np.inf)
    pos = np.searchsorted(ons, td, side="right")
    tn = np.where(pos < ons.size, ons[np.minimum(pos, ons.size - 1)] - td, np.inf)
    tn[pos >= ons.size] = np.inf
    return tn


def is_scorable(nap):
    if nap["t"].size == 0:
        return False
    if np.isinf(nap["first_onset"]):
        return True
    return nap["t"][0] <= nap["first_onset"] - PRE_ONSET_MIN


# ---------- sustain + record-high structure ----------

def windowed_min(t, score, S):
    """trailing (t_i-S, t_i] min of score; sustain_ok_i = window spans ~S seconds."""
    if S <= 0:
        return score.copy(), np.ones(t.size, bool)
    lo = np.searchsorted(t, t - S, side="left")
    wmin = np.array([score[lo[i]:i + 1].min() for i in range(t.size)])
    sustain_ok = (t - t[lo]) >= (S - TOL_SUSTAIN)
    return wmin, sustain_ok


def records(t, wmin, sok):
    """Strictly-increasing record-highs of sustained score, in time order.
    Returns (R ascending values, TT their times)."""
    if not sok.any():
        return np.array([]), np.array([])
    tt, vv = t[sok], wmin[sok]
    run_max = np.maximum.accumulate(vv)
    is_rec = np.empty(vv.size, bool)
    is_rec[0] = True
    is_rec[1:] = vv[1:] > run_max[:-1]
    return vv[is_rec], tt[is_rec]


def fire_time(R, TT, T):
    j = int(np.searchsorted(R, T, side="left"))
    return float(TT[j]) if j < R.size else None


def fire_grid(R, TT, grid):
    j = np.searchsorted(R, grid, side="left")
    out = np.full(grid.size, np.nan)
    ok = j < R.size
    out[ok] = TT[j[ok]]
    return out


def falsefire_value(t, wmin, sok, first_onset, early):
    if np.isinf(first_onset):
        region = sok
    else:
        region = sok & (t < first_onset - early)
    return float(wmin[region].max()) if region.any() else -np.inf


# ---------- model ----------

def fit_fold(train_nights, clf_kind):
    Xs, ys = [], []
    for nap in train_nights:
        m = nap["stage"] != N3
        Xs.append(nap["X"][m]); ys.append((tau_all(nap)[m] <= L_TRAIN).astype(int))
    X, y = np.vstack(Xs), np.concatenate(ys)
    if clf_kind == "logreg":
        sc = StandardScaler().fit(X)
        clf = LogisticRegression(max_iter=2000, class_weight="balanced").fit(sc.transform(X), y)
        return lambda M: clf.predict_proba(sc.transform(M))[:, 1]
    clf = RandomForestClassifier(class_weight="balanced_subsample", **RF_KW).fit(X, y)
    return lambda M: clf.predict_proba(M)[:, 1]


# ---------- experiment ----------

def run(clf_kind):
    nights = build_nights()
    subj = np.array([n["subj"] for n in nights])
    scorable = np.array([is_scorable(n) for n in nights])
    idx = np.arange(len(nights))

    cells = {}                      # (S,early,late,budget) -> [per-fold (hit,ff,late,miss)]
    pooled = []                     # per held-out nap: {onset, grid:{S:array101}}

    for tr, te in GroupKFold(n_splits=N_FOLDS).split(idx, groups=subj):
        train = [nights[i] for i in tr if scorable[i]]
        test = [nights[i] for i in te if scorable[i]]
        score = fit_fold(train, clf_kind)

        # cache sustained-score structure
        def prep(naps):
            out = []
            for n in naps:
                sc = score(n["X"])
                per_S = {}
                for S in SUSTAIN:
                    wmin, sok = windowed_min(n["t"], sc, S)
                    per_S[S] = (n["t"], wmin, sok) + records(n["t"], wmin, sok)
                out.append((n, per_S))
            return out
        tr_prep, te_prep = prep(train), prep(test)

        for S in SUSTAIN:
            for early in EARLY:
                vff = np.array([falsefire_value(d[S][0], d[S][1], d[S][2], n["first_onset"], early)
                                for n, d in tr_prep])
                vff = vff[np.isfinite(vff)]
                for b in BUDGETS:
                    T = float(np.quantile(vff, 1.0 - b)) if vff.size else 1.01
                    fts = [fire_time(d[S][3], d[S][4], T) for _, d in te_prep]
                    n_N3 = sum(1 for n, _ in te_prep if not np.isinf(n["first_onset"]))
                    n_all = len(te_prep)
                    for late in LATE:
                        hit = ef = lf = miss = nnff = 0
                        for (n, _), ft in zip(te_prep, fts):
                            on = n["first_onset"]
                            if np.isinf(on):
                                nnff += ft is not None
                            elif ft is None:
                                miss += 1
                            elif ft < on - early:
                                ef += 1
                            elif ft <= on + late:
                                hit += 1
                            else:
                                lf += 1
                        cells.setdefault((S, early, late, b), []).append(
                            (hit / n_N3 if n_N3 else np.nan, (ef + nnff) / n_all if n_all else np.nan,
                             lf / n_N3 if n_N3 else np.nan, miss / n_N3 if n_N3 else np.nan))

        for n, d in te_prep:
            pooled.append({"onset": n["first_onset"],
                           "grid": {S: fire_grid(d[S][3], d[S][4], T_GRID) for S in SUSTAIN}})

    # threshold-swept frontier (pooled held-out), vectorised over T_GRID
    onsets = np.array([p["onset"] for p in pooled])
    is_n3 = ~np.isinf(onsets)
    frontier = {}
    for S in SUSTAIN:
        FT = np.vstack([p["grid"][S] for p in pooled])      # (n_naps, 101)
        fired = ~np.isnan(FT)
        for early in EARLY:
            ef_mask = fired & is_n3[:, None] & (FT < (onsets[:, None] - early))
            nnff_mask = fired & (~is_n3)[:, None]
            ff = (ef_mask.sum(0) + nnff_mask.sum(0)) / FT.shape[0]
            for late in LATE:
                hit_mask = fired & is_n3[:, None] & (FT >= onsets[:, None] - early) & (FT <= onsets[:, None] + late)
                hit = hit_mask.sum(0) / max(is_n3.sum(), 1)
                frontier[(S, early, late)] = np.column_stack([T_GRID, ff, hit])
    return cells, frontier, int(scorable.sum()), len(nights), int(is_n3.sum())


def agg(recs):
    if not recs:
        return (np.nan,) * 4
    hit = np.array([r[0] for r in recs]); ff = np.array([r[1] for r in recs])
    return float(np.nanmean(hit)), float(np.nanmin(hit)), float(np.nanmax(hit)), float(np.nanmean(ff))


def main():
    print("Per-nap event-scoring surface — building (logreg)...")
    cells_lr, front_lr, n_score, n_tot, n_n3 = run("logreg")
    print(f"  scorable naps: {n_score}/{n_tot}  (of which N3 naps with usable pre-onset series: {n_n3})")

    print(f"\n{'='*96}\nHEADLINE 3x4 — hit rate @ 20% false-fire budget, sustain S=30s, logreg\n{'='*96}")
    print("  hit rate among N3 naps; held-out fold-mean[min..max]; (realized held-out FF)")
    print("  early\\late" + "".join(f"{'+'+str(int(l))+'s':>20}" for l in LATE))
    for early in EARLY:
        row = f"  {int(early/60)} min   "
        for late in LATE:
            m, lo, hi, ffr = agg(cells_lr.get((30.0, early, late, 0.20)))
            row += f"{m:.2f}[{lo:.2f}-{hi:.2f}]({ffr:.2f})".rjust(20)
        print(row)

    print("\n  building RF cross-check...")
    cells_rf, front_rf, _, _, _ = run("rf")
    print("  RF vs logreg (hit@20%FF, S=30) — flag divergence:")
    for early in EARLY:
        row = f"  {int(early/60)}min "
        for late in LATE:
            mlr = agg(cells_lr.get((30.0, early, late, 0.20)))[0]
            mrf = agg(cells_rf.get((30.0, early, late, 0.20)))[0]
            row += f"  +{int(late)}s L{mlr:.2f}/R{mrf:.2f}"
        print(row)

    # full cells CSV
    with open(f"{ROOT}/event_scoring_cells.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["model", "sustain_s", "early_s", "late_s", "ff_budget",
                    "hit_mean", "hit_min", "hit_max", "realized_ff_mean"])
        for tag, cells in (("logreg", cells_lr), ("rf", cells_rf)):
            for key in sorted(cells):
                S, early, late, b = key
                m, lo, hi, ffr = agg(cells[key])
                w.writerow([tag, int(S), int(early), int(late), b,
                            f"{m:.4f}", f"{lo:.4f}", f"{hi:.4f}", f"{ffr:.4f}"])
    # frontier CSV
    with open(f"{ROOT}/event_scoring_frontier.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["model", "sustain_s", "early_s", "late_s", "T", "ff_rate", "hit_rate"])
        for tag, front in (("logreg", front_lr), ("rf", front_rf)):
            for key in sorted(front):
                S, early, late = key
                for T, ff, hit in front[key]:
                    w.writerow([tag, int(S), int(early), int(late), f"{T:.3f}", f"{ff:.4f}", f"{hit:.4f}"])
    print(f"\n  wrote event_scoring_cells.csv, event_scoring_frontier.csv")

    # frontier PNG (logreg, S=30): 3 early panels, 4 late curves, budget points @ late=+60s
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.6), sharey=True)
    for ax, early in zip(axes, EARLY):
        for late, c in zip(LATE, ["C0", "C1", "C2", "C3"]):
            arr = front_lr[(30.0, early, late)]
            ax.plot(arr[:, 1], arr[:, 2], "-", color=c, lw=1.8, label=f"late=+{int(late)}s")
        for b in BUDGETS:
            m, lo, hi, ffr = agg(cells_lr.get((30.0, early, 60.0, b)))
            ax.errorbar([ffr], [m], yerr=[[max(m - lo, 0)], [max(hi - m, 0)]], fmt="ks", ms=6, capsize=3,
                        label=f"@{int(b*100)}%FF budget" if early == EARLY[0] else None)
        ax.axvline(0.20, color="grey", ls=":", lw=1)
        ax.set_title(f"early = {int(early/60)} min"); ax.set_xlabel("false-fire rate (naps)")
        ax.grid(alpha=0.3); ax.set_xlim(0, 0.6); ax.set_ylim(0, 1)
    axes[0].set_ylabel("hit rate (N3 naps, held-out)")
    axes[0].legend(fontsize=7, loc="lower right")
    fig.suptitle("Per-nap hit-vs-false-fire frontier (logreg, S=30s; budget op-points @ late=+60s)")
    fig.tight_layout(); fig.savefig(f"{ROOT}/event_scoring_frontier.png", dpi=130)
    print(f"  wrote event_scoring_frontier.png")
    print("\nDONE — surface stated. No operating point selected, no detector built (by request).")


if __name__ == "__main__":
    main()
