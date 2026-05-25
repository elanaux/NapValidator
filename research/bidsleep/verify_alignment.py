"""HR <-> label alignment verification on BidSleep.

Read-only. No training, no model fitting beyond a 1-D offset scan whose
purpose is to determine whether the doc's formula
    k = floor((t - recStart) / 30) + 1
correctly pairs HR samples with their stage labels.

PROBE: physiology. N3 (Deep) has low rolling-HR-SD; Wake has high. If the
labels are correctly aligned to the HR timeline, mean rolling-SD inside
N3-labeled epochs must be CLEARLY lower than inside Wake-labeled epochs.
If labels are shifted, the two distributions smear together (or invert).

PROCEDURE per night:
  1. Load hr.csv -> (t_unix, bpm), compute rolling-60s HR-SD.
  2. Parse recStart as UTC -> recStart_base. Define
        effective_recStart(offset) = recStart_base + offset
        k(t, offset) = floor((t - effective_recStart(offset)) / 30)
     so offset=0 reproduces the doc's formula exactly.
  3. Compute mean(SD | label=N3) and mean(SD | label=Wake) at offset=0
     and the separation = mean_Wake_SD - mean_N3_SD.
  4. Scan offsets in [-6h, +6h] at 30s step (= 1 epoch). For each
     offset re-bin labels to HR samples vectorially. Pick the offset
     that maximizes separation (subject to minimum sample-count thresholds
     in each stage bucket).
  5. Report whether offset=0 already gave clean separation, the
     best-fit offset, and the separation at best-fit.

ACROSS-NIGHT verdict:
  - If all sampled nights agree on best_offset to within ~30s, alignment
    is governed by a CONSTANT correction (or already correct at offset=0).
  - If best_offset varies across nights by minutes-to-hours, alignment is
    PER-NIGHT and the dataset is unusable until the per-night basis is
    determined.
  - If best_offset corresponds to a clean timezone value (+-N hours, with
    a tolerance for DST/sub-hour zones), recStart is local-time vs UTC and
    the fix is a simple zone normalisation.

NO training, NO model — alignment determination only.
"""
from __future__ import annotations

import csv
import os
import sys
from datetime import datetime, timezone

import numpy as np
from scipy.io import loadmat

# Import the canonical rolling-SD from the project so we use the EXACT same
# variability definition as the shape analysis. This guarantees the alignment
# probe is consistent with how we already characterise Deep vs Core.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_shape_hypothesis import rolling_sd_trailing  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))

# Sample selection: 5 different subjects spanning the HR-rate distribution.
# From the Q1 sweep:
#   - Bidslab38  3.97/min  (very sparse, would be density-gated)
#   - Bidslab22  6.63/min  (sparse)
#   - Bidslab00  9.97/min  (mid)
#   - Bidslab13 12.00/min  (dense)
#   - Bidslab60 12.01/min  (dense)
# First night of each.
NIGHTS = [
    ("Bidslab38", "1"),
    ("Bidslab22", "1"),
    ("Bidslab00", "1"),
    ("Bidslab13", "1"),
    ("Bidslab60", "1"),
]

WINDOW_SD = 60.0    # seconds; same as analyze_shape_hypothesis
EPOCH_S = 30.0
OFFSET_GRID_HOURS = 6.0
OFFSET_STEP_S = 30.0  # one epoch
MIN_PER_STAGE = 30    # min #HR samples per stage bucket to compute a mean

WAKE = 0
N3 = 3


def load_night(subj: str, night: str):
    hr_path = f"{ROOT}/{subj}/{night}/hr.csv"
    lab_path = f"{ROOT}/{subj}/{night}/labels.mat"
    t_list, bpm_list = [], []
    with open(hr_path) as f:
        for row in csv.reader(f):
            if len(row) < 2:
                continue  # skip blank / truncated rows (e.g. Bidslab42/3 line 12926: ts, no bpm)
            try:
                ts, b = float(row[0]), float(row[1])
            except ValueError:
                continue
            t_list.append(ts)
            bpm_list.append(b)
    order = np.argsort(t_list)
    t = np.asarray(t_list)[order]
    bpm = np.asarray(bpm_list)[order]

    m = loadmat(lab_path)
    labels = np.asarray(m["expert_label"]).flatten().astype(int)
    rs_str = str(m["recStart"][0])
    rs_utc = datetime.strptime(rs_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc).timestamp()
    return t, bpm, labels, rs_utc, rs_str


def mean_sd_per_stage(sd: np.ndarray, t: np.ndarray, labels: np.ndarray,
                      rs_base: float, offset: float):
    """At a given offset, bin every HR sample to its label epoch and return
    (mean_SD_in_N3, mean_SD_in_Wake, n_N3, n_Wake, n_in_range)."""
    effective = rs_base + offset
    k = np.floor((t - effective) / EPOCH_S).astype(np.int64)
    N = labels.size
    in_range = (k >= 0) & (k < N)
    if not in_range.any():
        return float("nan"), float("nan"), 0, 0, 0
    k_v = k[in_range]
    sd_v = sd[in_range]
    stage = labels[k_v]
    n3_m = (stage == N3)
    wk_m = (stage == WAKE)
    n_n3 = int(n3_m.sum())
    n_wk = int(wk_m.sum())
    n3_mean = float(sd_v[n3_m].mean()) if n_n3 >= MIN_PER_STAGE else float("nan")
    wk_mean = float(sd_v[wk_m].mean()) if n_wk >= MIN_PER_STAGE else float("nan")
    return n3_mean, wk_mean, n_n3, n_wk, int(in_range.sum())


def fmt_offset_s(off: float) -> str:
    sign = "+" if off >= 0 else "-"
    a = abs(off)
    h = int(a // 3600)
    m = int((a - h * 3600) // 60)
    s = a - h * 3600 - m * 60
    return f"{sign}{h:d}h{m:02d}m{s:05.2f}s"


def closest_clean_zone(offset_s: float) -> str:
    """Closest hour, half-hour and 45-min-zone match, with residual."""
    # standard offset values (seconds)
    candidates = {f"{h:+d}h": h * 3600 for h in range(-12, 15)}
    candidates.update({f"{h:+d}h30m": int(h * 3600 + 1800 * (1 if h >= 0 else -1)) for h in [-9, -3, 3, 5, 9, 10]})
    candidates["+5h45m"] = 5 * 3600 + 45 * 60
    candidates["+12h45m"] = 12 * 3600 + 45 * 60
    best = min(candidates.items(), key=lambda kv: abs(kv[1] - offset_s))
    residual = offset_s - best[1]
    return f"{best[0]} (residual {residual:+.1f}s)"


def verify_night(subj: str, night: str) -> dict:
    t, bpm, labels, rs_base, rs_str = load_night(subj, night)
    span_min = (t[-1] - t[0]) / 60.0
    rate = len(t) / span_min if span_min > 0 else 0.0
    n_ep = labels.size
    span_lab_min = n_ep * EPOCH_S / 60.0

    # Rolling SD (same definition the shape analysis uses)
    sd = rolling_sd_trailing(t, bpm, WINDOW_SD)
    valid = ~np.isnan(sd)
    sd_v = sd[valid]
    t_v = t[valid]

    # Offset=0 (doc formula as-is)
    n3_0, wk_0, n_n3_0, n_wk_0, n_in_0 = mean_sd_per_stage(sd_v, t_v, labels, rs_base, 0.0)
    sep_0 = wk_0 - n3_0 if not (np.isnan(n3_0) or np.isnan(wk_0)) else float("nan")

    # Offset scan
    offs = np.arange(-OFFSET_GRID_HOURS * 3600, OFFSET_GRID_HOURS * 3600 + OFFSET_STEP_S, OFFSET_STEP_S)
    seps = np.full(offs.size, np.nan)
    n3_means = np.full(offs.size, np.nan)
    wk_means = np.full(offs.size, np.nan)
    n_in = np.zeros(offs.size, dtype=int)
    for i, off in enumerate(offs):
        n3_m, wk_m, _, _, ni = mean_sd_per_stage(sd_v, t_v, labels, rs_base, float(off))
        n3_means[i] = n3_m
        wk_means[i] = wk_m
        n_in[i] = ni
        if not (np.isnan(n3_m) or np.isnan(wk_m)):
            seps[i] = wk_m - n3_m

    # Best-fit offset (max separation)
    if np.all(np.isnan(seps)):
        best_off, best_sep, n3_best, wk_best = float("nan"), float("nan"), float("nan"), float("nan")
    else:
        i_best = int(np.nanargmax(seps))
        best_off = float(offs[i_best])
        best_sep = float(seps[i_best])
        n3_best = float(n3_means[i_best])
        wk_best = float(wk_means[i_best])

    # Plateau analysis: how many candidate offsets are within 5% of best?
    if not np.isnan(best_sep):
        plateau = (~np.isnan(seps)) & (seps >= 0.95 * best_sep)
        n_plateau = int(plateau.sum())
        plateau_span_s = float((offs[plateau].max() - offs[plateau].min()))
    else:
        n_plateau = 0
        plateau_span_s = float("nan")

    return {
        "subject": subj, "night": night, "recStart_str": rs_str,
        "rate_per_min": rate, "span_min": span_min,
        "n_ep": n_ep, "span_lab_min": span_lab_min,
        "n_hr": len(t),
        "n3_sd_0": n3_0, "wake_sd_0": wk_0, "sep_0": sep_0,
        "n_n3_0": n_n3_0, "n_wk_0": n_wk_0, "n_in_range_0": n_in_0,
        "best_off_s": best_off, "best_sep": best_sep,
        "n3_sd_best": n3_best, "wake_sd_best": wk_best,
        "plateau_n": n_plateau, "plateau_span_s": plateau_span_s,
        "offs": offs, "seps": seps,
    }


def main() -> None:
    results = [verify_night(s, n) for s, n in NIGHTS]

    print()
    print("=" * 120)
    print("HR <-> label alignment verification on BidSleep")
    print("=" * 120)
    print(f"Probe: rolling-{int(WINDOW_SD)}s HR-SD mean inside N3-labeled epochs vs Wake-labeled epochs.")
    print(f"Higher (Wake_SD - N3_SD) = sharper alignment.  Offset scan: ±{OFFSET_GRID_HOURS:.0f}h, step {int(OFFSET_STEP_S)}s.")
    print(f"recStart parsed as UTC; offset is added on top of that (so offset=0 reproduces the doc formula exactly).")

    print()
    hdr = (
        f"{'subject':10s} {'night':5s} {'rate/m':>6s} {'n_HR':>5s} {'n_ep':>5s}  "
        f"{'N3_SD@0':>8s} {'Wake_SD@0':>10s} {'sep@0':>7s}  "
        f"{'best_off':>14s} {'N3_SD@b':>8s} {'Wake_SD@b':>10s} {'sep@b':>7s}  "
        f"{'plateau(s)':>11s}"
    )
    print(hdr)
    print("-" * len(hdr))
    for r in results:
        print(
            f"{r['subject']:10s} {r['night']:5s} {r['rate_per_min']:6.2f} {r['n_hr']:5d} {r['n_ep']:5d}  "
            f"{r['n3_sd_0']:8.3f} {r['wake_sd_0']:10.3f} {r['sep_0']:7.3f}  "
            f"{fmt_offset_s(r['best_off_s']):>14s} {r['n3_sd_best']:8.3f} {r['wake_sd_best']:10.3f} {r['best_sep']:7.3f}  "
            f"{r['plateau_span_s']:11.1f}"
        )

    print()
    print("Per-night detail")
    print("-" * 120)
    for r in results:
        sign_at_0 = ("aligned" if r["sep_0"] > 0 else "INVERTED") if not np.isnan(r["sep_0"]) else "n/a"
        zone = closest_clean_zone(r["best_off_s"]) if not np.isnan(r["best_off_s"]) else "n/a"
        print(f"  {r['subject']}/{r['night']}  recStart='{r['recStart_str']}'  span_HR={r['span_min']:.1f}min  span_lab={r['span_lab_min']:.1f}min")
        print(f"     offset=0 :  N3_SD={r['n3_sd_0']:.3f}  Wake_SD={r['wake_sd_0']:.3f}  sep={r['sep_0']:+.3f}  "
              f"({sign_at_0}; {r['n_n3_0']} N3 samples, {r['n_wk_0']} Wake samples, {r['n_in_range_0']} in range)")
        print(f"     best-fit :  offset={fmt_offset_s(r['best_off_s'])} ({r['best_off_s']:+.1f}s)  sep={r['best_sep']:+.3f}  "
              f"plateau within 5%: {r['plateau_n']} bins, span={r['plateau_span_s']:.1f}s")
        print(f"                 nearest clean zone: {zone}")

    # ---- VERDICT ----
    print()
    print("=" * 120)
    print("VERDICT")
    print("=" * 120)
    best_offs = np.array([r["best_off_s"] for r in results if not np.isnan(r["best_off_s"])])
    seps_0 = np.array([r["sep_0"] for r in results if not np.isnan(r["sep_0"])])
    seps_best = np.array([r["best_sep"] for r in results if not np.isnan(r["best_sep"])])

    if best_offs.size == 0:
        print("Could not determine alignment on any sampled night (insufficient HR or stage coverage).")
        return

    # (a) Does offset=0 give clean separation on all nights?
    if np.all(seps_0 > 0):
        all_pos = True
        median_sep_0 = float(np.median(seps_0))
    else:
        all_pos = False
        median_sep_0 = float(np.median(seps_0))

    # (b) Is best-fit offset roughly constant?
    off_spread = float(best_offs.max() - best_offs.min())

    # (c) Improvement from offset=0 to best-fit
    improvements = []
    for r in results:
        if not (np.isnan(r["sep_0"]) or np.isnan(r["best_sep"])):
            improvements.append(r["best_sep"] - r["sep_0"])
    median_improvement = float(np.median(improvements)) if improvements else float("nan")

    print(f"Offset-0 separation across {seps_0.size} nights: "
          f"median={median_sep_0:+.3f}  min={seps_0.min():+.3f}  max={seps_0.max():+.3f}  "
          f"all-positive={all_pos}")
    print(f"Best-fit offset across {best_offs.size} nights: "
          f"median={np.median(best_offs):+.1f}s  spread (max - min)={off_spread:.1f}s")
    print(f"Median improvement (sep@best - sep@0): {median_improvement:+.3f}")
    print()

    # Classification
    if all_pos and median_improvement < 0.1 * abs(median_sep_0 + 1e-9):
        print("CLASSIFICATION:  offset=0 ALREADY YIELDS CLEAN ALIGNMENT on every sampled night.")
        print("                 The doc formula is correct as-is; no per-night correction needed.")
        print("                 The +14480s 'recStart vs first HR' residual seen earlier reflects the")
        print("                 Apple Watch recording starting BEFORE the EEG session, not a clock mismatch.")
    elif off_spread <= 60.0:
        print(f"CLASSIFICATION:  CONSTANT OFFSET across all sampled nights (spread {off_spread:.1f}s ≤ 60s).")
        med = float(np.median(best_offs))
        print(f"                 Apply a fixed correction of {fmt_offset_s(med)} ({med:+.1f}s) to recStart "
              f"before computing k.")
    else:
        print(f"CLASSIFICATION:  PER-NIGHT OFFSETS — spread {off_spread:.1f}s "
              f"({off_spread/60:.1f}m, {off_spread/3600:.2f}h) across {best_offs.size} nights.")
        print(f"                 Cannot use a single global correction. Either fit per-night via this same")
        print(f"                 N3-vs-Wake SD probe, or determine the per-night basis from authors' code")
        print(f"                 before treating labels as ground truth.")

    # Timezone hypothesis
    print()
    zone_residuals = [r["best_off_s"] - round(r["best_off_s"] / 3600) * 3600 for r in results if not np.isnan(r["best_off_s"])]
    max_zr = max(abs(z) for z in zone_residuals)
    if max_zr <= 60.0:
        print(f"TIMEZONE check:  every best-fit offset is within {max_zr:.0f}s of an integer-hour boundary"
              f" — consistent with recStart being LOCAL time (UTC vs local mismatch).")
    else:
        print(f"TIMEZONE check:  best-fit offsets do NOT collapse to integer-hour boundaries "
              f"(max residual {max_zr:.0f}s) — not a simple timezone issue.")


if __name__ == "__main__":
    main()
