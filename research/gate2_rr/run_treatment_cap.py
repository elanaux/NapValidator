"""Gate 2 Step 4 — TREATMENT vs BASELINE on CAP, scored against the pre-registered bar.

Everything is fixed in gate-2-preregistration.md (incl. Amendments 1-6); nothing here
is tuned. Per usable record, at every 5 s decision point t, the HRV features use only
clean NN intervals whose beat time is <= t (strictly trailing):
  ln_rmssd_60 — ln RMSSD over (t-60, t]; successive differences only between
                adjacent clean NN
  sdnn_300    — SD of clean NN over (t-300, t]
  ln_hf_300   — ln HF power 0.15-0.40 Hz over (t-300, t]
  lf_hf_300   — ln(LF/HF), LF 0.04-0.15 Hz
Validity: clean-NN duration covers >= 80 % of the window. Spectral: the window's
own clean beats, cubic-spline to 4 Hz, Welch (Hann, 128 s = 512-sample segments,
50 % overlap).

Both arms are evaluated on the COMMON row set (every baseline + treatment feature
finite), so the GroupKFold(5) folds are identical and the lift is paired per fold.
"""
from __future__ import annotations

import os
import sys
from multiprocessing import Pool

import numpy as np
from scipy.interpolate import CubicSpline
from scipy.signal import welch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "bidsleep"))
sys.path.insert(0, HERE)
from leadtime_harness import (  # noqa: E402  (unchanged harness)
    night_features, onset_times, cv_scores, EPOCH_S, N3, UNKNOWN, L_READ,
)
from run_baseline_cap import usable_records, DERIVED  # noqa: E402

HRV_NAMES = ["ln_rmssd_60", "sdnn_300", "ln_hf_300", "lf_hf_300"]
BASE_NAMES = ["sd_60", "drop_vs_base", "slope_120"]
COVER = 0.80
FS_I = 4.0
NPERSEG = 512
PASS_MEAN, FAIL_MEAN = 0.04, 0.02
GAP_GROW = 0.03


# ---------- causal HRV features ----------

def hrv_features(rr_t, rr_ms, keep, t_dec):
    """HRV features at each decision time in t_dec, from clean NN with beat time <= t."""
    tk, nn = rr_t[keep], rr_ms[keep]
    # adjacency: clean NN i and its predecessor are consecutive RR in the raw series
    idx = np.flatnonzero(keep)
    adj = np.concatenate([[False], np.diff(idx) == 1])
    sd2 = np.concatenate([[np.nan], np.diff(nn)]) ** 2
    c_nn = np.concatenate([[0.0], np.cumsum(nn)])
    c_nn2 = np.concatenate([[0.0], np.cumsum(nn * nn)])
    c_sd2 = np.concatenate([[0.0], np.cumsum(np.where(adj, sd2, 0.0))])
    c_adj = np.concatenate([[0], np.cumsum(adj)])
    hi = np.searchsorted(tk, t_dec, side="right")           # beats with time <= t
    out = np.full((t_dec.size, 4), np.nan)
    for w, col in ((60.0, 0), (300.0, 1)):
        lo = np.searchsorted(tk, t_dec - w, side="right")   # time > t - w
        n = hi - lo
        cover = (c_nn[hi] - c_nn[lo]) / 1000.0 >= COVER * w
        if col == 0:
            # successive differences whose BOTH beats are inside the window -> exclude first beat's pair
            lo1 = np.minimum(lo + 1, hi)
            na = c_adj[hi] - c_adj[lo1]
            ok = cover & (na >= 2)
            with np.errstate(invalid="ignore", divide="ignore"):
                out[ok, 0] = np.log(np.sqrt((c_sd2[hi] - c_sd2[lo1])[ok] / na[ok]))
        else:
            ok = cover & (n >= 3)
            s, s2 = (c_nn[hi] - c_nn[lo])[ok], (c_nn2[hi] - c_nn2[lo])[ok]
            m = n[ok]
            out[ok, 1] = np.sqrt(np.maximum(s2 - s * s / m, 0) / (m - 1))
            # spectral, per valid point
            for j in np.flatnonzero(ok):
                a, b = lo[j], hi[j]
                bt, bv = tk[a:b], nn[a:b]
                if bt.size < 8 or np.any(np.diff(bt) <= 0):
                    continue
                g = np.arange(bt[0], bt[-1], 1.0 / FS_I)
                if g.size < NPERSEG:
                    continue
                x = CubicSpline(bt, bv)(g)
                f, p = welch(x, fs=FS_I, window="hann", nperseg=NPERSEG, noverlap=NPERSEG // 2)
                df = f[1] - f[0]
                lf = p[(f >= 0.04) & (f < 0.15)].sum() * df
                hf = p[(f >= 0.15) & (f <= 0.40)].sum() * df
                if hf > 0 and lf > 0:
                    out[j, 2] = np.log(hf)
                    out[j, 3] = np.log(lf / hf)
    return out


def record_rows(rec):
    """Decision-point table for one record: baseline + HRV features, stage, tau_next, tau_first."""
    z = np.load(os.path.join(DERIVED, f"{rec}.npz"))
    t, bpm, labels, rs = z["hr_t"], z["hr_bpm"].astype(float), z["labels"], float(z["rs"])
    N = labels.size
    Xb, ok = night_features(t, bpm)
    k = np.floor((t - rs) / EPOCH_S).astype(np.int64)
    valid = ok & (k >= 0) & (k < N)
    vi = np.flatnonzero(valid)
    st = labels[k[vi]]
    keep = st != UNKNOWN
    vi, st = vi[keep], st[keep]
    td = t[vi]
    Xh = hrv_features(z["rr_t"], z["rr_ms"], z["rr_keep"].astype(bool), td)
    ons = onset_times(labels, rs, 0)
    if ons.size:
        pos = np.searchsorted(ons, td, side="right")
        tn = np.where(pos < ons.size, ons[np.minimum(pos, ons.size - 1)] - td, np.inf)
        tn[pos >= ons.size] = np.inf
        tf = ons[0] - td
    else:
        tn = np.full(td.size, np.inf)
        tf = np.full(td.size, np.inf)
    return rec, np.hstack([Xb[vi], Xh]), st, tn, tf


# ---------- scoring ----------

def fold_avg(X, mask, tau, groups, clf):
    """per-fold AUROC averaged over read-L (the pre-registered summary), plus per-L detail."""
    Xs, taus, grp = X[mask], tau[mask], groups[mask]
    perL, ap = [], []
    for L in L_READ:
        y = (taus <= float(L)).astype(int)
        au, apr = cv_scores(Xs, y, grp, clf)
        assert len(au) == 5, f"fold without positives at L={L}"
        perL.append(np.array(au)); ap.append(np.mean(apr))
    return np.mean(np.vstack(perL), axis=0), np.vstack(perL), np.array(ap)


def bar(d):
    if d.mean() >= PASS_MEAN and (d > 0).all():
        return "PASS"
    if d.mean() < FAIL_MEAN or (d <= 0).sum() >= 2:
        return "FAIL"
    return "INCONCLUSIVE"


def evaluate(recs, tag, groups, X, stage, tn, tf):
    B = list(range(3))
    T = list(range(7))
    nonN3 = stage != N3
    first = nonN3 & (tf > 0)
    print(f"\n{'='*100}\n{tag}: {X.shape[0]:,} common-row decision points, "
          f"{len(np.unique(groups))} subjects\n{'='*100}")
    res = {}
    for lab, mask, tau in (("all-N3", nonN3, tn), ("first-N3-only (informational)", first, tf)):
        for clf in ("logreg", "rf"):
            fb, pb, apb = fold_avg(X[:, B], mask, tau, groups, clf)
            ft, pt, apt = fold_avg(X[:, T], mask, tau, groups, clf)
            d = ft - fb
            res[(lab, clf)] = (fb, ft, d)
            print(f"\n  {lab} — {clf}   ({mask.sum():,} points)")
            print(f"  {'L(s)':>5} {'base':>7} {'treat':>7} {'Δ':>7}  {'AUPRC b/t':>13}   per-fold Δ")
            for i, L in enumerate(L_READ):
                print(f"  {L:>5} {pb[i].mean():>7.3f} {pt[i].mean():>7.3f} {pt[i].mean()-pb[i].mean():>+7.3f}"
                      f"  {apb[i]:.3f}/{apt[i]:.3f}   " + " ".join(f"{v:+.3f}" for v in pt[i] - pb[i]))
            print(f"  avg over read-L — baseline per-fold: " + " ".join(f"{v:.3f}" for v in fb)
                  + f"  (mean {fb.mean():.3f})")
            print(f"                    treatment per-fold: " + " ".join(f"{v:.3f}" for v in ft)
                  + f"  (mean {ft.mean():.3f}, min {ft.min():.3f})")
            print(f"                    paired lift Δ:      " + " ".join(f"{v:+.3f}" for v in d)
                  + f"  (mean {d.mean():+.3f}, positive in {(d > 0).sum()}/5)")
    y0 = (stage == N3).astype(int)
    for nm, cols in (("baseline", B), ("treatment", T)):
        au, _ = cv_scores(X[:, cols], y0, groups, "logreg")
        print(f"  L=0 N3-vs-rest (EXCLUDED) {nm}: logreg AUROC {np.mean(au):.3f}")
    return res


def main():
    recs = usable_records()
    with Pool(max(1, os.cpu_count() - 1)) as pool:
        out = pool.map(record_rows, [r for r, _ in recs])
    fs = dict(recs)
    subj = np.concatenate([np.full(o[1].shape[0], o[0]) for o in out])
    X = np.vstack([o[1] for o in out])
    stage = np.concatenate([o[2] for o in out])
    tn = np.concatenate([o[3] for o in out])
    tf = np.concatenate([o[4] for o in out])
    common = np.isfinite(X).all(axis=1)
    print(f"usable subjects: {len(recs)};  decision points (baseline-valid): {X.shape[0]:,};  "
          f"common row set: {common.sum():,} ({100*common.mean():.1f}%)")
    for i, nm in enumerate(HRV_NAMES):
        v = X[common, 3 + i]
        print(f"  {nm:12s} finite {100*np.isfinite(X[:, 3+i]).mean():5.1f}%   "
              f"p5/p50/p95 {np.percentile(v, 5):.3f} / {np.percentile(v, 50):.3f} / {np.percentile(v, 95):.3f}")
    lost = sorted(set(subj) - set(subj[common]))
    if lost:
        print(f"  subjects with no common rows: {lost}")

    X, subj, stage, tn, tf = X[common], subj[common], stage[common], tn[common], tf[common]
    prim = evaluate(recs, "PRIMARY — all usable subjects", subj, X, stage, tn, tf)

    hi = np.array([fs[s] >= 200 for s in subj])
    sub = evaluate([r for r in recs if r[1] >= 200], "SENSITIVITY — >=200 Hz subset (non-gating)",
                   subj[hi], X[hi], stage[hi], tn[hi], tf[hi])

    # ---------- verdict (pre-registered logic) ----------
    lr_d = prim[("all-N3", "logreg")][2]
    rf_d = prim[("all-N3", "rf")][2]
    lr_v, rf_meets = bar(lr_d), bar(rf_d) == "PASS"
    if lr_v == "PASS":
        verdict = "PASS — RR carries lead-time signal beyond averaged HR -> proceed to MESA (NOT a usefulness claim)"
    elif rf_meets:
        verdict = "INCONCLUSIVE — nonlinear signal (routes to MESA; not a pass)"
    else:
        verdict = lr_v
    sub_d = sub[("all-N3", "logreg")][2]
    sub_meets = bar(sub_d) == "PASS"
    if lr_v != "PASS" and sub_meets:   # can move FAIL/INCONCLUSIVE, never creates or removes a PASS
            verdict += "  +  INCONCLUSIVE — possible sampling-rate attenuation (routes to MESA)"
    fb_lr, ft_lr, _ = prim[("all-N3", "logreg")]
    fb_rf, ft_rf, _ = prim[("all-N3", "rf")]
    grow = (ft_rf - ft_lr) - (fb_rf - fb_lr)
    broken = grow.mean() >= GAP_GROW and (grow > 0).sum() >= 4

    print(f"\n{'#'*100}\nPRE-REGISTERED VERDICT  (all-N3; usable CAP subjects = {len(recs)})\n{'#'*100}")
    print(f"  LR paired lift (GATE):  " + " ".join(f"{v:+.3f}" for v in lr_d)
          + f"   mean {lr_d.mean():+.3f}, positive {(lr_d > 0).sum()}/5  -> {lr_v}")
    print(f"  RF paired lift:         " + " ".join(f"{v:+.3f}" for v in rf_d)
          + f"   mean {rf_d.mean():+.3f}, positive {(rf_d > 0).sum()}/5  -> meets bar: {rf_meets}")
    print(f"  >=200 Hz LR lift:       " + " ".join(f"{v:+.3f}" for v in sub_d)
          + f"   mean {sub_d.mean():+.3f}, positive {(sub_d > 0).sum()}/5  -> meets bar: {sub_meets} (non-gating)")
    print(f"  bar: PASS mean>=+0.04 & 5/5 positive; FAIL mean<+0.02 or >=2 non-positive; else INCONCLUSIVE")
    print(f"\n  VERDICT: {verdict}")
    print(f"\n  Signal-limited (Amendment 6, reported): RF-LR gap baseline {np.mean(fb_rf - fb_lr):+.3f}, "
          f"treatment {np.mean(ft_rf - ft_lr):+.3f}; growth " + " ".join(f"{v:+.3f}" for v in grow)
          + f" (mean {grow.mean():+.3f}, growing {(grow > 0).sum()}/5) -> "
          f"{'BROKEN by RR' if broken else 'persists (w.r.t. RR)'}")
    print(f"  Absolute (informational, cross-dataset bar 0.65/0.60): treatment LR mean {ft_lr.mean():.3f}, "
          f"fold-min {ft_lr.min():.3f}")


if __name__ == "__main__":
    main()
