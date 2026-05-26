"""Early-tail of onset-to-Deep (data-light surfacing pass).

Reuses the LOCKED BidSleep alignment + the onset-to-Deep series computed in
onset_variance_pull.py (imported, NOT re-derived). Descriptive only.

Frame: 42 subjects with >=2 N3 nights (within-subject).
  personal_mean   = mean onset-to-Deep across that subject's nights (in-sample).
  early_dev       = personal_mean - night_o2d, kept only where > 0 (earlier than own mean).
  firing model    = countdown fires at (personal_mean - margin) min after sleep onset.
                    GROGGY WAKE (failure) if night_o2d < (personal_mean - margin),
                    i.e. Deep arrived before the countdown fired.
                    depth_into_Deep = (personal_mean - margin) - night_o2d  (min past N3 onset)
                    nap_sacrificed (non-failure) = night_o2d - (personal_mean - margin)

NOTE printed: personal_mean is IN-SAMPLE (includes the night being scored); a deployed
system would not have the current night in its mean, so the real early-rate is plausibly
a touch higher than reported here.
CAVEAT printed: BidSleep is OVERNIGHT, not naps.
"""
from __future__ import annotations
import os, sys
from collections import defaultdict
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from onset_variance_pull import usable_nights, night_metrics  # locked logic

ROOT = "/Users/elanaux/Desktop/nap-app"
MARGINS = [0, 2, 4, 6]
HARD_SD = 10.0  # "hard-swinging" = within-subject SD > 10 min (yesterday's ~19% cut)


def qstats(x):
    x = np.asarray([v for v in x if v == v], float)
    if x.size == 0:
        return None
    q1, med, q3 = np.percentile(x, [25, 50, 75])
    return dict(n=int(x.size), min=float(x.min()), q1=float(q1), median=float(med),
                q3=float(q3), max=float(x.max()), mean=float(x.mean()),
                sd=float(x.std(ddof=1)) if x.size > 1 else float("nan"))


def line(label, s, unit="min"):
    if s is None:
        print(f"  {label}: (none)"); return
    print(f"  {label}: n={s['n']}  min={s['min']:.1f}  Q1={s['q1']:.1f}  "
          f"median={s['median']:.1f}  Q3={s['q3']:.1f}  max={s['max']:.1f}  "
          f"mean={s['mean']:.1f}  SD={s['sd']:.1f}  {unit}")


def build():
    """Return by_subj: subj -> np.array of onset-to-Deep (min), >=2 N3 nights only."""
    by_subj = defaultdict(list)
    for s, n in usable_nights():
        r = night_metrics(s, n)
        if r is None:
            continue
        _lat, d = r
        if d is not None:
            by_subj[s].append(d)
    return {s: np.asarray(v, float) for s, v in by_subj.items() if len(v) >= 2}


def main():
    bs = build()
    subs = sorted(bs)
    n_subj = len(subs)
    all_nights = sum(len(v) for v in bs.values())
    print("=" * 80)
    print("EARLY-TAIL OF ONSET-TO-DEEP  (BidSleep, locked alignment; descriptive only)")
    print("=" * 80)
    print("CAVEAT: BidSleep is OVERNIGHT, not naps. Naps self-select for sleep-deprived")
    print("        states that may pull Deep EARLIER and make it MORE variable, so the")
    print("        real nap early-tail is plausibly WORSE than these numbers.")
    print("NOTE:   personal_mean is in-sample (includes the scored night); a deployed")
    print("        per-user mean would not, so real early-rate is plausibly a touch higher.")
    print(f"\nSubjects: {n_subj}  |  total N3 nights: {all_nights}")

    pmean = {s: bs[s].mean() for s in subs}
    psd = {s: bs[s].std(ddof=1) for s in subs}
    hard = {s for s in subs if psd[s] > HARD_SD}
    print(f"'Hard-swinging' subjects (within-subj SD > {HARD_SD:.0f} min): "
          f"{len(hard)}/{n_subj} ({len(hard)/n_subj*100:.0f}%) -> {sorted(hard)}")

    # ---- 2. EARLY DEVIATIONS ONLY ----
    print("\n" + "-" * 80)
    print("[2] EARLY DEVIATIONS (personal_mean - night_o2d, positive only)")
    print("-" * 80)
    early_pooled = []
    worst_per_subj = []
    n_early = 0
    for s in subs:
        dev = pmean[s] - bs[s]            # + = earlier than own mean
        e = dev[dev > 0]
        early_pooled.extend(e.tolist())
        n_early += int((dev > 0).sum())
        worst_per_subj.append(float(dev.max()) if dev.size else 0.0)
    frac_early = n_early / all_nights
    print(f"  Fraction of all nights that are EARLY (o2d < own mean): "
          f"{n_early}/{all_nights} = {frac_early*100:.0f}%")
    print("  Pooled early-deviation magnitude (min earlier than own mean):")
    line("    pooled-early", qstats(early_pooled))
    print("  WORST early deviation per subject (each person's worst groggy-wake night):")
    line("    worst-per-subj", qstats(worst_per_subj))

    # ---- 3. FIRING-RELATIVE SWEEP ----
    print("\n" + "-" * 80)
    print("[3] FIRING SWEEP: fire at (personal_mean - margin); failure if Deep beats it")
    print("-" * 80)
    print(f"  {'margin':>6s} {'fail%':>6s} {'n_fail':>6s} | "
          f"{'depth-into-Deep (min past N3): med [Q1,Q3] max':<46s} | "
          f"{'nap sacrificed (min)':>22s}")
    sweep = {}
    for m in MARGINS:
        depths, sacrifice_nonfail, sacrifice_all = [], [], []
        n_fail = 0
        fail_by_subj = defaultdict(int)
        for s in subs:
            fire = pmean[s] - m
            for d in bs[s]:
                if d < fire:                 # FAILURE: Deep before fire
                    n_fail += 1
                    depths.append(fire - d)  # min past N3 onset
                    sacrifice_all.append(0.0)
                    fail_by_subj[s] += 1
                else:                        # non-failure: woke before Deep
                    sac = d - fire
                    sacrifice_nonfail.append(sac)
                    sacrifice_all.append(sac)
        fail_rate = n_fail / all_nights
        ds = qstats(depths)
        sac_nf = float(np.mean(sacrifice_nonfail)) if sacrifice_nonfail else float("nan")
        sac_all = float(np.mean(sacrifice_all))
        depth_str = (f"med {ds['median']:.1f} [{ds['q1']:.1f},{ds['q3']:.1f}] max {ds['max']:.1f}"
                     if ds else "(no failures)")
        print(f"  {m:6d} {fail_rate*100:5.1f}% {n_fail:6d} | {depth_str:<46s} | "
              f"nonfail {sac_nf:5.1f} / all {sac_all:4.1f}")
        sweep[m] = dict(fail_rate=fail_rate, n_fail=n_fail, depths=depths,
                        sac_nonfail=sac_nf, sac_all=sac_all, fail_by_subj=dict(fail_by_subj),
                        depth_stats=ds)
    print("  (depth-into-Deep = how many min past N3 onset the fire lands, on failure nights)")
    print("  (nap sacrificed: 'nonfail' = mean over non-failure nights; 'all' = mean over all")
    print("   nights counting failures as 0 sacrifice. baseline guaranteed cost ~= margin.)")

    # ---- 4. TAIL CONCENTRATION ----
    print("\n" + "-" * 80)
    print("[4] TAIL CONCENTRATION: do failures come from the hard-swingers?")
    print("-" * 80)
    hard_night_share = sum(len(bs[s]) for s in hard) / all_nights
    print(f"  Hard-swingers are {len(hard)}/{n_subj} subjects holding "
          f"{hard_night_share*100:.0f}% of all nights (the 'even-spread' baseline).")
    print(f"  {'margin':>6s} {'n_fail':>6s} {'%fail from hard':>16s} {'%fail from rest':>16s}")
    tail = {}
    for m in MARGINS:
        fb = sweep[m]["fail_by_subj"]
        nf = sweep[m]["n_fail"]
        from_hard = sum(c for s, c in fb.items() if s in hard)
        sh = (from_hard / nf) if nf else float("nan")
        print(f"  {m:6d} {nf:6d} {sh*100:15.0f}% {(1-sh)*100 if nf else float('nan'):15.0f}%")
        tail[m] = sh
    print(f"  (even-spread expectation = {hard_night_share*100:.0f}% if failures were "
          f"proportional to night count)")

    figures(bs, subs, pmean, hard, sweep, early_pooled, worst_per_subj, all_nights)


def figures(bs, subs, pmean, hard, sweep, early_pooled, worst_per_subj, all_nights):
    fig, ax = plt.subplots(2, 2, figsize=(12, 9))

    a = ax[0, 0]
    a.hist(early_pooled, bins=25, color="#cc6677", edgecolor="w")
    a.axvline(np.median(early_pooled), color="k", ls="--", lw=1,
              label=f"median {np.median(early_pooled):.1f}m")
    a.set_title(f"Pooled EARLY deviations (n={len(early_pooled)} early nights)\nmin earlier than own mean")
    a.set_xlabel("min early"); a.legend()

    a = ax[0, 1]
    a.hist(worst_per_subj, bins=15, color="#882255", edgecolor="w")
    a.axvline(10, color="r", lw=1.5, label="10 min")
    a.set_title("Worst early night per subject (churn-risk tail)")
    a.set_xlabel("min early"); a.legend()

    a = ax[1, 0]
    margins = MARGINS
    fr = [sweep[m]["fail_rate"] * 100 for m in margins]
    sac = [sweep[m]["sac_nonfail"] for m in margins]
    a.plot(margins, fr, "o-", color="#ee6677", label="failure rate %")
    a.set_xlabel("margin (min fired early)"); a.set_ylabel("groggy-wake failure %", color="#ee6677")
    a.tick_params(axis="y", labelcolor="#ee6677")
    a2 = a.twinx()
    a2.plot(margins, sac, "s--", color="#4477aa", label="nap sacrificed (nonfail) min")
    a2.set_ylabel("mean nap sacrificed, non-fail (min)", color="#4477aa")
    a2.tick_params(axis="y", labelcolor="#4477aa")
    a.set_title("Failure-rate vs lost-sleep tradeoff")
    a.set_xticks(margins)

    a = ax[1, 1]
    # depth-into-Deep boxplot per margin (failures only)
    data = [sweep[m]["depths"] if sweep[m]["depths"] else [0] for m in margins]
    a.boxplot(data, labels=[str(m) for m in margins], showfliers=True)
    a.set_title("Depth into Deep on failure nights\n(min past N3 onset the fire lands)")
    a.set_xlabel("margin (min)"); a.set_ylabel("min into Deep")

    fig.suptitle("Onset-to-Deep early-tail — BidSleep OVERNIGHT proxy (naps plausibly worse)",
                 fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.96])
    out = f"{ROOT}/research/early_tail.png"
    fig.savefig(out, dpi=120)
    print(f"\nFigure saved: {out}")


if __name__ == "__main__":
    main()
