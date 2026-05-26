"""Depth-threshold sensitivity sweep (data-light, NO new data).

Reuses early_tail_pull.build() -> the 42 subjects (>=2 N3 nights), their
onset-to-Deep series, and personal_mean. Locked alignment. Surface only.

REFRAME (locked):
  This sweeps the acceptable-depth threshold to show how sensitive the failure
  rate is to where the 'still-an-acceptable-wake' line is drawn. NO threshold is
  treated as correct -- the true line (how many minutes into Deep still feels
  non-groggy to a user) is an unresolved empirical question that only field
  wake-ratings can answer. This is sensitivity analysis, not goalpost-setting.

Two knobs:
  margin in {0,2,4,6}: fire at (personal_mean - margin).
  D in {0,1,2,3,5}: a night is a FAILURE only if wake lands > D min past N3 onset.
  depth = (personal_mean - margin) - night_o2d   (min past N3 onset; <=0 = before Deep)
  FAILURE  iff depth > D.
  D=0 reproduces the prior run's failure rates exactly (anchor / cross-check).
"""
from __future__ import annotations
import os, sys
from collections import defaultdict
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from early_tail_pull import build, HARD_SD

ROOT = "/Users/elanaux/Desktop/nap-app"
MARGINS = [0, 2, 4, 6]
DS = [0, 1, 2, 3, 5]

REFRAME = (
    "This sweeps the acceptable-depth threshold to show how sensitive the failure\n"
    "rate is to where the 'still-an-acceptable-wake' line is drawn. NO threshold is\n"
    "treated as correct -- the true line (how many minutes into Deep still feels\n"
    "non-groggy to a user) is an unresolved empirical question that only field\n"
    "wake-ratings can answer. This is sensitivity analysis, not goalpost-setting."
)


def main():
    bs = build()                      # subj -> np.array onset-to-Deep (min), >=2 nights
    subs = sorted(bs)
    all_nights = sum(len(v) for v in bs.values())
    pmean = {s: bs[s].mean() for s in subs}
    psd = {s: bs[s].std(ddof=1) for s in subs}
    hard = {s for s in subs if psd[s] > HARD_SD}

    print("=" * 82)
    print("DEPTH-THRESHOLD SENSITIVITY SWEEP")
    print("=" * 82)
    print(REFRAME)
    print("-" * 82)
    print("CAVEAT: BidSleep is OVERNIGHT, not naps (real-nap early-tail plausibly worse);")
    print("        personal_mean is in-sample (deployed rate plausibly higher); and the")
    print("        acceptable-depth D is a TOLERANCE under test, NOT a validated comfort")
    print("        threshold.")
    print("-" * 82)
    print(f"Frame: {len(subs)} subjects, {all_nights} N3 nights. "
          f"Hard-swingers (within-subj SD>{HARD_SD:.0f}): {len(hard)}/{len(subs)}.")

    # precompute depth per (margin, night)
    depth = {m: [] for m in MARGINS}        # list of depths across all nights
    depth_subj = {m: [] for m in MARGINS}   # parallel subject id
    for m in MARGINS:
        for s in subs:
            fire = pmean[s] - m
            for d in bs[s]:
                depth[m].append(fire - d)
                depth_subj[m].append(s)
    depth = {m: np.asarray(v, float) for m, v in depth.items()}

    # ---- 4x5 failure-rate grid ----
    print("\n[GRID] Failure rate %  (failure = wake lands > D min past N3 onset)")
    print("       rows = margin (min fired early); cols = D (acceptable-depth tolerance, min)")
    print("       [D=0] column = ANCHOR, matches prior run exactly.\n")
    header = "  margin |" + "".join(f"  D={d:<2d}" + ("*" if d == 0 else " ") for d in DS)
    print(header)
    print("  " + "-" * (len(header) - 2))
    fail_grid = np.zeros((len(MARGINS), len(DS)))
    nfail_grid = np.zeros((len(MARGINS), len(DS)), int)
    for i, m in enumerate(MARGINS):
        dv = depth[m]
        cells = []
        for j, D in enumerate(DS):
            nf = int((dv > D).sum())
            fr = nf / all_nights * 100
            fail_grid[i, j] = fr
            nfail_grid[i, j] = nf
            cells.append(f"{fr:5.1f}")
        print(f"  {m:6d} |" + "".join(f" {c} " for c in cells))
    print("  (* D=0 anchor: failure = any wake at all past N3 onset = prior run's numbers)")
    print("\n[n failures] same grid, counts:")
    print(header)
    for i, m in enumerate(MARGINS):
        print(f"  {m:6d} |" + "".join(f" {nfail_grid[i,j]:4d}" + "  " for j in range(len(DS))))

    # ---- #3 within-band breakdown ----
    print("\n[WITHIN-BAND] of the 'acceptable' wakes (depth<=D), how many genuinely")
    print("  land BEFORE Deep (depth<=0) vs IN the tolerance band (0<depth<=D)?")
    print("  (before-Deep count is D-independent; band count grows with D.)")
    print(f"  {'margin':>6s} {'D':>2s} | {'accept_n':>8s} {'before-Deep':>11s} "
          f"{'in-band(0<d<=D)':>15s} {'%band of accept':>15s} | {'fail_n':>6s}")
    for m in MARGINS:
        dv = depth[m]
        before = int((dv <= 0).sum())   # D-independent
        for D in DS:
            accept = int((dv <= D).sum())
            band = int(((dv > 0) & (dv <= D)).sum())
            fail = int((dv > D).sum())
            pct = (band / accept * 100) if accept else float("nan")
            print(f"  {m:6d} {D:2d} | {accept:8d} {before:11d} {band:15d} "
                  f"{pct:14.0f}% | {fail:6d}")

    # ---- #4 nap sacrificed (D-independent) ----
    print("\n[COST] nap sacrificed is margin-driven and D-INDEPENDENT")
    print("  (D only relabels in-Deep wakes; minutes of pre-Deep nap given up is unchanged).")
    print(f"  {'margin':>6s} {'sacrificed nonfail (min)':>24s} {'sacrificed all (min)':>22s}")
    for m in MARGINS:
        dv = depth[m]                      # depth = fire - o2d
        before_mask = dv <= 0              # woke before Deep
        sac_each = -dv                     # = o2d - fire, positive when before Deep
        sac_nonfail = float(sac_each[before_mask].mean()) if before_mask.any() else float("nan")
        sac_all = float(np.clip(sac_each, 0, None).mean())
        print(f"  {m:6d} {sac_nonfail:23.1f} {sac_all:21.1f}")
    print("  (bigger margin = fewer failures = more sleep sacrificed; the tradeoff still applies.)")

    # ---- #5 tail at representative cell (margin 4, D 3) ----
    M5, D5 = 4, 3
    dv = depth[M5]; sj = np.asarray(depth_subj[M5])
    fail_mask = dv > D5
    nf = int(fail_mask.sum())
    from_hard = int(sum(1 for s in sj[fail_mask] if s in hard))
    hard_night_share = sum(len(bs[s]) for s in hard) / all_nights
    print(f"\n[TAIL] representative cell margin={M5}, D={D5}:  {nf} residual failures")
    if nf:
        print(f"  from hard-swingers: {from_hard}/{nf} = {from_hard/nf*100:.0f}%  | "
              f"from rest: {nf-from_hard}/{nf} = {(nf-from_hard)/nf*100:.0f}%")
    print(f"  even-spread baseline = {hard_night_share*100:.0f}% (hard-swingers' share of nights)")

    figure(fail_grid)


def figure(fail_grid):
    fig, ax = plt.subplots(figsize=(8.5, 5.2))
    im = ax.imshow(fail_grid, cmap="OrRd", aspect="auto", vmin=0, vmax=fail_grid.max())
    ax.set_xticks(range(len(DS))); ax.set_xticklabels([f"D={d}" for d in DS])
    ax.set_yticks(range(len(MARGINS))); ax.set_yticklabels([f"margin {m}" for m in MARGINS])
    for i in range(len(MARGINS)):
        for j in range(len(DS)):
            v = fail_grid[i, j]
            ax.text(j, i, f"{v:.1f}", ha="center", va="center",
                    color="white" if v > fail_grid.max() * 0.55 else "black",
                    fontsize=11, fontweight="bold")
    # flag D=0 anchor column
    ax.add_patch(plt.Rectangle((-0.5, -0.5), 1, len(MARGINS), fill=False,
                               edgecolor="#1f78b4", lw=2.5))
    ax.text(0, -0.62, "anchor\n(=prior run)", ha="center", va="bottom",
            fontsize=8, color="#1f78b4")
    ax.set_xlabel("acceptable-depth tolerance D (min past N3 onset)")
    ax.set_ylabel("safety margin (min fired early)")
    ax.set_title("Groggy-wake failure rate (%) — depth-threshold sensitivity\n"
                 "BidSleep OVERNIGHT proxy; D is a TESTED tolerance, not a validated threshold",
                 fontsize=10)
    fig.colorbar(im, label="failure rate %")
    fig.tight_layout()
    out = f"{ROOT}/research/depth_sensitivity.png"
    fig.savefig(out, dpi=120)
    print(f"\nFigure saved: {out}")


if __name__ == "__main__":
    main()
