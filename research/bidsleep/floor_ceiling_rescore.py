"""Floor+Ceiling RE-SCORE of the event-scoring surface — offline, no retrain.

NOT a new model. Reuses, byte-for-byte where possible, the event-scoring probe's
machinery (event_scoring.py): same aligned BidSleep corpus, same subject-level
GroupKFold(5), same 3 causal features, same per-sample logreg score trained on the
all-N3 lead-time label at L_TRAIN=300 s, same sustain/threshold (record-high) firing
machinery. ONLY THE FIRING REGION CHANGES.

THE GATE (product parameters, locked grid; NOT fit to data):
  floor F   (min from sleep onset): detector muzzled before F  (= minimum guaranteed sleep)
  ceiling C (min from sleep onset): if no detector fire by C, a timer fires at C (failsafe;
             every nap ends). The timer-fire is NOT a detector catch and NOT a false-fire —
             it is just "the nap ended without a detector decision".
  F in {8,10,12,15} min;  C in {20,25,30} min;  all F<C cells.

SLEEP ONSET (the F/C anchor): HR-time of the first SCORED-SLEEP epoch
  (label in {N1,N2,N3,REM}; not Wake=0, not Unknown=5), placed on the HR timeline with the
  night's locked offset:  t0 = rs + (e_sleep + m_best)*EPOCH_S — same mapping onset_times uses.
  t_floor = t0 + F*60 ; t_ceiling = t0 + C*60.

OPERATING POINT — leak-guard UNCHANGED (interpretation note):
  T* is the SAME threshold the ungated probe used: the (1-b) quantile of TRAIN-nap ungated
  false-fire values v at the anchor early (set on train, applied to held-out). We do NOT
  re-budget on the gated region — that would re-target b by construction and there would be
  nothing to "cut". Holding T* fixed is what makes output #2 ("fraction of the ORIGINAL
  false-fires eliminated by the floor, by construction") well posed, and answers output #1
  ("how much does muzzling the pre-floor region cut the budgeted FF") directly. The gate is
  then applied identically to every nap (train and test) when locating fires.

ANCHOR: acceptance early=7min(420s)/late=+60s, sustain S=30s, logreg. Budget sweep
  {10,20,30%} reported in CSV; headline at 20%. (On this corpus ALL scorable naps are N3
  naps, so a false-fire = an N3 nap that fires before onset-early.)

FIRE-ONCE outcome of a nap (per cell), detector restricted to [t_floor, t_ceiling]:
  fire_g = first sustained crossing of T* with t in [t_floor, t_ceiling]; else timer@C.
  N3 nap: fire_g<onset-early => EARLY-FALSE-FIRE; <=onset+late => HIT; else => LATE-FIRE;
          no detector fire => timer@C (no catch, no false-fire).

THE FOUR OUTPUTS (per F×C cell, held-out, fold spread retained):
  1. realized FF gated vs ungated.
  2. decomposition of the ORIGINAL (ungated) false-fires: removed-by-floor (<F) /
     remaining-in-[F,C] / removed-by-ceiling (>C).  (pooled held-out)
  3. early-Deep failures: scorable N3 naps with first onset < F min from sleep onset
     (detector muzzled through the descent => guaranteed miss; timer can't catch either).
     Model-independent; depends only on F.
  4. catch rate within [F,C] vs ungated catch.
PLUS once: distribution of first-N3-onset times (min from sleep onset) over the scorable naps.

NO verdict. NO recommended (F,C). NO detector built. The read is the user's.
"""
from __future__ import annotations

import csv
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from sklearn.model_selection import GroupKFold

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# reuse the EXACT machinery from the event-scoring probe / harness
from leadtime_harness import load_usable, night_features, onset_times, EPOCH_S, UNKNOWN  # noqa: E402
from verify_alignment import load_night, WAKE  # noqa: E402
from event_scoring import (is_scorable, windowed_min, falsefire_value, fit_fold,  # noqa: E402
                           N_FOLDS)

# locked gate grid + anchor
FLOORS = [8.0, 10.0, 12.0, 15.0]      # minutes from sleep onset
CEILS = [20.0, 25.0, 30.0]            # minutes from sleep onset
EARLY_ANCHOR = 420.0                  # 7 min acceptance lead
LATE_ANCHOR = 60.0                    # +60 s acceptance lag
S_ANCHOR = 30.0                       # sustain
BUDGETS = [0.10, 0.20, 0.30]
HEADLINE_B = 0.20
PRIOR_UNGATED = {0.10: None, 0.20: (0.1817, 0.2034), 0.30: None}  # (catch,FF) anchor cell from event_scoring_cells.csv


# ---------- corpus (event_scoring.build_nights + sleep-onset HR-time) ----------

def build_nights_t0():
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
        sleep_eps = np.flatnonzero((labels != WAKE) & (labels != UNKNOWN))
        sleep_onset = float(rs + (sleep_eps[0] + m_best) * EPOCH_S) if sleep_eps.size else np.inf
        nights.append({"subj": s, "night": night, "t": td, "X": X[vi], "stage": st,
                       "first_onset": first_onset, "ons": ons, "sleep_onset": sleep_onset})
    return nights


# ---------- firing + outcome ----------

def first_cross(t, wmin, sok, T, lo=-np.inf, hi=np.inf):
    """earliest decision-point time with sustained score >= T inside [lo,hi]; None if none."""
    m = sok & (wmin >= T) & (t >= lo) & (t <= hi)
    return float(t[m][0]) if m.any() else None   # t ascending => [0] is earliest


def classify(ft, onset, early, late):
    """fire-once outcome. ft=None => no detector fire (ungated miss / gated timer@C)."""
    if ft is None:
        return "nofire"
    if ft < onset - early:
        return "ff"        # fired in the too-early region
    if ft <= onset + late:
        return "hit"
    return "late"          # overshot Deep


def spread(vals):
    a = np.array(vals, float)
    return float(np.nanmean(a)), float(np.nanmin(a)), float(np.nanmax(a))


# ---------- experiment ----------

def run(clf_kind):
    nights = build_nights_t0()
    subj = np.array([n["subj"] for n in nights])
    scorable = np.array([is_scorable(n) for n in nights])
    idx = np.arange(len(nights))

    cells = {}     # (F,C,b) -> [per-fold (catch_g, ff_g)]
    ung = {}       # b       -> [per-fold (catch_u, ff_u)]
    pooled = []    # per held-out nap per b: dict(b, sleep_onset, first_onset, fire_ung)

    for tr, te in GroupKFold(n_splits=N_FOLDS).split(idx, groups=subj):
        train = [nights[i] for i in tr if scorable[i]]
        test = [nights[i] for i in te if scorable[i]]
        score = fit_fold(train, clf_kind)

        def prep(naps):
            out = []
            for n in naps:
                sc = score(n["X"])
                wmin, sok = windowed_min(n["t"], sc, S_ANCHOR)
                out.append((n, n["t"], wmin, sok))
            return out
        tr_prep, te_prep = prep(train), prep(test)
        n_all = len(te_prep)

        for b in BUDGETS:
            # T* — unchanged leak-guard: (1-b) quantile of TRAIN ungated false-fire values
            vff = np.array([falsefire_value(t, wmin, sok, n["first_onset"], EARLY_ANCHOR)
                            for (n, t, wmin, sok) in tr_prep])
            vff = vff[np.isfinite(vff)]
            T = float(np.quantile(vff, 1.0 - b)) if vff.size else 1.01

            # ungated reference + remember per-nap ungated fire
            hit_u = ff_u = 0
            for (n, t, wmin, sok) in te_prep:
                fu = first_cross(t, wmin, sok, T)
                c = classify(fu, n["first_onset"], EARLY_ANCHOR, LATE_ANCHOR)
                hit_u += c == "hit"; ff_u += c == "ff"
                pooled.append({"b": b, "sleep_onset": n["sleep_onset"],
                               "first_onset": n["first_onset"], "fire_ung": fu})
            ung.setdefault(b, []).append((hit_u / n_all, ff_u / n_all))

            # gated cells
            for F in FLOORS:
                for C in CEILS:
                    hit_g = ff_g = 0
                    for (n, t, wmin, sok) in te_prep:
                        t0 = n["sleep_onset"]
                        fg = first_cross(t, wmin, sok, T, t0 + F * 60.0, t0 + C * 60.0)
                        c = classify(fg, n["first_onset"], EARLY_ANCHOR, LATE_ANCHOR)
                        hit_g += c == "hit"; ff_g += c == "ff"
                    cells.setdefault((F, C, b), []).append((hit_g / n_all, ff_g / n_all))

    return cells, ung, pooled, nights, scorable


def decompose(pooled, b, F, C):
    """Pooled held-out: split the ORIGINAL (ungated) false-fires by where they fell."""
    ff = [p for p in pooled if p["b"] == b and p["fire_ung"] is not None
          and p["fire_ung"] < p["first_onset"] - EARLY_ANCHOR]
    n = len(ff)
    rem_floor = sum(1 for p in ff if p["fire_ung"] < p["sleep_onset"] + F * 60.0)
    rem_ceil = sum(1 for p in ff if p["fire_ung"] > p["sleep_onset"] + C * 60.0)
    return n, rem_floor, n - rem_floor - rem_ceil, rem_ceil


def onset_minutes(nights, scorable):
    return np.array([(n["first_onset"] - n["sleep_onset"]) / 60.0
                     for n, sc in zip(nights, scorable) if sc and np.isfinite(n["first_onset"])])


# ---------- report ----------

def main():
    print("Floor+ceiling re-score (no retrain) — building corpus + logreg held-out fires...")
    cells, ung, pooled, nights, scorable = run("logreg")
    n_score = int(scorable.sum())
    om = onset_minutes(nights, scorable)

    # ---- SANITY: ungated anchor must reproduce event_scoring_cells.csv (catch .1817 / FF .2034) ----
    cu, fu = spread([u[0] for u in ung[HEADLINE_B]])[0], spread([u[1] for u in ung[HEADLINE_B]])[0]
    pc, pf = PRIOR_UNGATED[HEADLINE_B]
    ok = abs(cu - pc) < 5e-4 and abs(fu - pf) < 5e-4
    print(f"\nSANITY ungated anchor (early=420,late=60,S=30,b=20%): catch={cu:.4f} (prior {pc}), "
          f"FF={fu:.4f} (prior {pf})  -> {'MATCH' if ok else 'MISMATCH!!'}")
    if not ok:
        print("  STOP: ungated baseline does not reproduce the prior surface; gate comparison invalid.")
        return

    # ---- onset distribution (once) ----
    qs = np.percentile(om, [0, 25, 50, 75, 100])
    print(f"\n{'='*92}\nFIRST-N3-ONSET DISTRIBUTION (minutes from sleep onset) — {om.size} scorable naps\n{'='*92}")
    print(f"  min={qs[0]:.1f}  Q1={qs[1]:.1f}  median={qs[2]:.1f}  Q3={qs[3]:.1f}  max={qs[4]:.1f}  (mean={om.mean():.1f})")
    print("  naps with onset BELOW each candidate floor F (these are amputated by that floor):")
    for F in FLOORS:
        nb = int((om < F).sum())
        print(f"     F={int(F):2d} min : {nb:2d}/{om.size}  ({100*nb/om.size:.0f}%)")

    # ---- headline table @ 20% ----
    print(f"\n{'='*92}\nHEADLINE @ budget {int(HEADLINE_B*100)}% — realized FF (gated) and catch within [F,C], held-out fold-mean[min..max]\n{'='*92}")
    print(f"  ungated reference @20%: FF={fu:.3f}  catch={cu:.3f}   (no floor, no ceiling)")
    for metric, ix in (("realized false-fire (gated)", 1), ("catch within [F,C]", 0)):
        print(f"\n  {metric}:")
        print("   F\\C " + "".join(f"{'C='+str(int(C)):>20}" for C in CEILS))
        for F in FLOORS:
            row = f"  {int(F):2d}m "
            for C in CEILS:
                m, lo, hi = spread([r[ix] for r in cells[(F, C, HEADLINE_B)]])
                row += f"{m:.2f}[{lo:.2f}-{hi:.2f}]".rjust(20)
            print(row)

    # ---- original-false-fire decomposition @ 20% (pooled) ----
    print(f"\n{'='*92}\nORIGINAL (ungated) FALSE-FIRE DECOMPOSITION @ budget {int(HEADLINE_B*100)}% (pooled held-out)\n{'='*92}")
    print("  of the ungated too-early fires: how many a floor F removes (<F), how many remain in [F,C], how many a ceiling C removes (>C)")
    print("   F\\C " + "".join(f"{'C='+str(int(C)):>22}" for C in CEILS))
    for F in FLOORS:
        row = f"  {int(F):2d}m "
        for C in CEILS:
            n, rf, win, rc = decompose(pooled, HEADLINE_B, F, C)
            row += f"{rf}f/{win}in/{rc}c (of {n})".rjust(22)
        print(row)

    # ---- early-Deep failures (model-independent) ----
    print(f"\n{'='*92}\nEARLY-DEEP FAILURES (model-independent) — scorable N3 naps with onset < F\n{'='*92}")
    for F in FLOORS:
        nb = int((om < F).sum())
        print(f"  F={int(F):2d} min : {nb:2d}/{om.size} naps ({100*nb/om.size:.0f}%) muzzled through their descent -> guaranteed miss")

    # ---- RF cross-check (optional) ----
    print("\nRF cross-check (catch/FF @20%, S=30, late=60) — flag divergence:")
    cells_rf, ung_rf, _, _, _ = run("rf")
    cur, fur = spread([u[0] for u in ung_rf[HEADLINE_B]])[0], spread([u[1] for u in ung_rf[HEADLINE_B]])[0]
    print(f"  ungated: logreg catch {cu:.2f}/FF {fu:.2f}   vs   RF catch {cur:.2f}/FF {fur:.2f}")

    # ---- CSV ----
    path = f"{ROOT}/floor_ceiling_cells.csv"
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["model", "floor_min", "ceil_min", "budget", "early_s", "late_s", "sustain_s",
                    "gated_ff_mean", "gated_ff_min", "gated_ff_max",
                    "gated_catch_mean", "gated_catch_min", "gated_catch_max",
                    "ungated_ff_mean", "ungated_catch_mean",
                    "orig_ff_n", "ff_removed_floor", "ff_remain_window", "ff_removed_ceil",
                    "early_deep_fail_n", "early_deep_fail_frac", "n_scorable"])
        for tag, cc, uu in (("logreg", cells, ung), ("rf", cells_rf, ung_rf)):
            for b in BUDGETS:
                ucatch = spread([u[0] for u in uu[b]])[0]
                uff = spread([u[1] for u in uu[b]])[0]
                for F in FLOORS:
                    edf = int((om < F).sum())
                    for C in CEILS:
                        cm, clo, chi = spread([r[0] for r in cc[(F, C, b)]])   # catch
                        fm, flo, fhi = spread([r[1] for r in cc[(F, C, b)]])   # ff
                        n, rf, win, rc = decompose(pooled, b, F, C)            # decomposition (logreg pooled)
                        w.writerow([tag, int(F), int(C), b, int(EARLY_ANCHOR), int(LATE_ANCHOR), int(S_ANCHOR),
                                    f"{fm:.4f}", f"{flo:.4f}", f"{fhi:.4f}",
                                    f"{cm:.4f}", f"{clo:.4f}", f"{chi:.4f}",
                                    f"{uff:.4f}", f"{ucatch:.4f}",
                                    n, rf, win, rc, edf, f"{edf/om.size:.4f}", n_score])
    print(f"\nwrote {os.path.basename(path)}")

    # ---- onset-distribution figure ----
    fig, ax = plt.subplots(figsize=(10, 5.2))
    ax.hist(om, bins=np.arange(0, np.ceil(om.max()) + 2, 2), color="#9ecae1", edgecolor="#3182bd")
    for F in FLOORS:
        nb = int((om < F).sum())
        ax.axvline(F, color="C3", ls="--", lw=1.6)
        ax.text(F, ax.get_ylim()[1] * 0.97, f"F={int(F)}\n({nb} below)", color="C3",
                fontsize=8, ha="center", va="top")
    for C in CEILS:
        ax.axvline(C, color="C0", ls=":", lw=1.6)
        ax.text(C, ax.get_ylim()[1] * 0.55, f"C={int(C)}", color="C0", fontsize=8, ha="center")
    ax.set_xlabel("first N3 onset (minutes from sleep onset)")
    ax.set_ylabel(f"# scorable naps (n={om.size})")
    ax.set_title("Where the floor can sit without amputating early-Deep naps\n"
                 "first-N3-onset distribution; red dashed = candidate floors F, blue dotted = candidate ceilings C")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(f"{ROOT}/floor_ceiling_onset_dist.png", dpi=130)
    print(f"wrote floor_ceiling_onset_dist.png")
    print("\nDONE — surface reported. No verdict, no recommended (F,C), no detector built (by request).")


if __name__ == "__main__":
    main()
