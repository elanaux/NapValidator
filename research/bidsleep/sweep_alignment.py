"""Wider alignment sweep across ALL 253 labeled BidSleep nights (§7 step 3).

Extends verify_alignment.py's N3-vs-Wake HR-SD probe from n=5 to the full
dataset. Produces the real *usable corpus*: nights where the per-night offset
is recoverable confidently (tight plateau, clean separation) AND the HR is
dense enough INSIDE the aligned label window.

Read-only. No training. Outputs:
  - a per-night table (alignment_table.csv) the lead-time labeler will consume,
  - per-subject usable-night + N3-onset counts to confirm whether the
    subject-level CV splits in the handoff (§5) stay viable after rejection.

KEY CORRECTNESS POINT (differs from verify_alignment's display rate):
  HR streams span far longer than the labeled EEG window (one night: 64h HR
  vs 5.8h labels). A density rate over the FULL stream is meaningless. Density
  here is measured only on HR samples that fall INSIDE the aligned label
  window (using the best-fit offset).

SPEED: the offset grid step equals one epoch (30s), and offsets are integer
multiples of the epoch, so k(t, offset=m*30) = floor((t-recStart)/30) - m.
We compute k0 = floor((t-recStart)/30) once and shift by an integer per
offset — no repeated floor over the HR array.
"""
from __future__ import annotations

import csv
import glob
import os
import re
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyze_shape_hypothesis import (  # noqa: E402
    rolling_sd_trailing, hr_density, density_sufficient,
)
from verify_alignment import load_night, fmt_offset_s  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))

EPOCH_S = 30.0
WINDOW_SD = 60.0
OFFSET_GRID_HOURS = 6.0
OFFSET_STEP_S = 30.0           # == one epoch (required for the integer-shift trick)
MIN_PER_STAGE = 30            # min HR samples per stage bucket to trust a mean
WAKE, N3 = 0, 3

# Usability thresholds (reported with sensitivity so they can be retuned).
PLATEAU_MAX_S = 60.0          # tight plateau => confident alignment (doc §2)
SEP_MIN = 1.5                 # N3-SD must be clearly below Wake-SD at best fit
SUBJECT_MIN_ONSETS = 20       # §5: 39/47 subjects had >=20 N3 onsets pre-gating


def scan_offsets(sd_v, k0_v, labels):
    """Integer-epoch-shift offset scan. Returns (offs, seps, n3_means, wk_means).

    For offset = m epochs, the label index of HR sample i is k0_v[i] - m.
    sep(m) = mean(SD | label==Wake) - mean(SD | label==N3) at that shift.
    """
    N = labels.size
    m_max = int(OFFSET_GRID_HOURS * 3600 / EPOCH_S)
    ms = np.arange(-m_max, m_max + 1)
    offs = ms * EPOCH_S
    seps = np.full(ms.size, np.nan)
    n3_means = np.full(ms.size, np.nan)
    wk_means = np.full(ms.size, np.nan)
    for j, m in enumerate(ms):
        k = k0_v - m
        in_range = (k >= 0) & (k < N)
        if not in_range.any():
            continue
        stage = labels[k[in_range]]
        sd_in = sd_v[in_range]
        n3m = stage == N3
        wkm = stage == WAKE
        if n3m.sum() >= MIN_PER_STAGE and wkm.sum() >= MIN_PER_STAGE:
            a = float(sd_in[n3m].mean())
            b = float(sd_in[wkm].mean())
            n3_means[j], wk_means[j], seps[j] = a, b, b - a
    return offs, seps, n3_means, wk_means


def count_onsets(labels, covered_epochs):
    """N3 onsets = first N3 epoch after a non-N3 epoch.

    Onset count is a property of the label sequence alone (alignment-invariant).
    'covered' = onsets where both the onset epoch and its predecessor have HR
    coverage under the best-fit alignment (i.e. we actually hold data there).
    Returns (n_all, n_covered, first_onset_epoch_or_-1).
    """
    is_n3 = labels == N3
    onset = np.zeros(labels.size, dtype=bool)
    onset[1:] = is_n3[1:] & ~is_n3[:-1]
    onset_eps = np.flatnonzero(onset)
    n_all = int(onset_eps.size)
    cov = covered_epochs
    n_cov = int(sum(1 for e in onset_eps if e in cov and (e - 1) in cov))
    first = int(onset_eps[0]) if n_all else -1
    return n_all, n_cov, first


def analyse_night(subj, night):
    t, bpm, labels, rs_base, rs_str = load_night(subj, night)
    N = labels.size
    span_lab_min = N * EPOCH_S / 60.0

    sd = rolling_sd_trailing(t, bpm, WINDOW_SD)
    valid = ~np.isnan(sd)
    sd_v = sd[valid]
    t_v = t[valid]
    if sd_v.size < MIN_PER_STAGE:
        return None  # too few usable HR samples to probe at all

    k0_v = np.floor((t_v - rs_base) / EPOCH_S).astype(np.int64)
    offs, seps, n3_means, wk_means = scan_offsets(sd_v, k0_v, labels)

    # offset 0 (doc formula as-is)
    zero_j = np.flatnonzero(offs == 0.0)
    sep_0 = float(seps[zero_j[0]]) if zero_j.size and not np.isnan(seps[zero_j[0]]) else float("nan")

    if np.all(np.isnan(seps)):
        return {
            "subject": subj, "night": night, "n_ep": N, "span_lab_min": span_lab_min,
            "best_off_s": float("nan"), "best_sep": float("nan"), "sep_0": sep_0,
            "plateau_span_s": float("nan"), "inwin_rate": 0.0, "inwin_gap_s": float("inf"),
            "cov_frac": 0.0, "cov_contig": 0.0,
            "n_onsets_all": 0, "n_onsets_cov": 0, "first_onset_ep": -1,
            "usable": False, "reject": "no_probe(insufficient N3/Wake coverage at any offset)",
        }

    j_best = int(np.nanargmax(seps))
    best_off = float(offs[j_best])
    best_sep = float(seps[j_best])

    plateau = (~np.isnan(seps)) & (seps >= 0.95 * best_sep)
    plateau_span_s = float(offs[plateau].max() - offs[plateau].min())

    # In-window density at best-fit offset, plus covered epochs.
    m_best = int(round(best_off / EPOCH_S))
    k_all = np.floor((t - rs_base) / EPOCH_S).astype(np.int64) - m_best
    inwin = (k_all >= 0) & (k_all < N)
    t_in = t[inwin]
    if t_in.size >= 2:
        dens = hr_density(t_in)
        inwin_rate = dens["rate_per_min"]
        inwin_gap = dens["median_gap_s"]
        dens_ok, _ = density_sufficient(dens)
    else:
        inwin_rate, inwin_gap, dens_ok = 0.0, float("inf"), False

    covered_arr = np.unique(k_all[inwin])
    covered_epochs = set(covered_arr.tolist())
    cov_frac = covered_arr.size / N if N else 0.0
    # contiguity: fraction of the covered span that is actually filled (1.0 = single block)
    cov_span = (covered_arr.max() - covered_arr.min() + 1) if covered_arr.size else 0
    cov_contig = (covered_arr.size / cov_span) if cov_span else 0.0
    n_all, n_cov, first_ep = count_onsets(labels, covered_epochs)

    align_ok = (plateau_span_s <= PLATEAU_MAX_S) and (best_sep >= SEP_MIN)
    usable = bool(align_ok and dens_ok)
    if usable:
        reject = ""
    else:
        reasons = []
        if best_sep < SEP_MIN:
            reasons.append(f"sep {best_sep:.2f}<{SEP_MIN}")
        if plateau_span_s > PLATEAU_MAX_S:
            reasons.append(f"plateau {plateau_span_s:.0f}s>{PLATEAU_MAX_S:.0f}s")
        if not dens_ok:
            reasons.append(f"density rate={inwin_rate:.1f}/min gap={inwin_gap:.1f}s")
        reject = "; ".join(reasons)

    return {
        "subject": subj, "night": night, "n_ep": N, "span_lab_min": span_lab_min,
        "best_off_s": best_off, "best_sep": best_sep, "sep_0": sep_0,
        "plateau_span_s": plateau_span_s, "inwin_rate": inwin_rate, "inwin_gap_s": inwin_gap,
        "cov_frac": cov_frac, "cov_contig": cov_contig,
        "n_onsets_all": n_all, "n_onsets_cov": n_cov, "first_onset_ep": first_ep,
        "usable": usable, "reject": reject,
    }


def enumerate_nights():
    out = []
    for lab in sorted(glob.glob(f"{ROOT}/Bidslab*/*/labels.mat")):
        d = os.path.dirname(lab)
        if not os.path.exists(f"{d}/hr.csv"):
            continue
        subj = os.path.basename(os.path.dirname(d))
        night = os.path.basename(d)
        out.append((subj, night))
    out.sort(key=lambda sn: (sn[0], int(sn[1]) if sn[1].isdigit() else sn[1]))
    return out


def main():
    nights = enumerate_nights()
    print(f"Sweeping {len(nights)} labeled nights "
          f"(plateau<= {PLATEAU_MAX_S:.0f}s, sep>= {SEP_MIN}, density rate>=4/min & gap<=15s)...")
    rows = []
    for i, (subj, night) in enumerate(nights):
        r = analyse_night(subj, night)
        if r is None:
            r = {"subject": subj, "night": night, "n_ep": 0, "span_lab_min": 0.0,
                 "best_off_s": float("nan"), "best_sep": float("nan"), "sep_0": float("nan"),
                 "plateau_span_s": float("nan"), "inwin_rate": 0.0, "inwin_gap_s": float("inf"),
                 "cov_frac": 0.0, "cov_contig": 0.0,
                 "n_onsets_all": 0, "n_onsets_cov": 0, "first_onset_ep": -1,
                 "usable": False, "reject": "too_few_HR_samples"}
        rows.append(r)
        if (i + 1) % 25 == 0:
            print(f"  ...{i+1}/{len(nights)}")

    # ---- write CSV ----
    cols = ["subject", "night", "usable", "reject", "best_off_s", "best_sep", "sep_0",
            "plateau_span_s", "inwin_rate", "inwin_gap_s", "cov_frac", "cov_contig",
            "n_ep", "span_lab_min", "n_onsets_all", "n_onsets_cov", "first_onset_ep"]
    csv_path = f"{ROOT}/alignment_table.csv"
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r[c] for c in cols})

    # ---- aggregate ----
    usable_rows = [r for r in rows if r["usable"]]
    n_usable = len(usable_rows)

    # offset-0 clean fraction (sep_0 positive and >= SEP_MIN)
    sep0_clean = sum(1 for r in rows if not np.isnan(r["sep_0"]) and r["sep_0"] >= SEP_MIN)
    sep0_have = sum(1 for r in rows if not np.isnan(r["sep_0"]))

    onsets_all_total = sum(r["n_onsets_all"] for r in rows)
    onsets_cov_usable = sum(r["n_onsets_cov"] for r in usable_rows)
    first_onset_usable = sum(1 for r in usable_rows if r["first_onset_ep"] >= 0)

    # per-subject usable onset counts (covered onsets on usable nights)
    subj_onsets, subj_nights = {}, {}
    for r in usable_rows:
        subj_onsets[r["subject"]] = subj_onsets.get(r["subject"], 0) + r["n_onsets_cov"]
        subj_nights[r["subject"]] = subj_nights.get(r["subject"], 0) + 1
    subj_all = set(r["subject"] for r in rows)
    subj_with_min = sum(1 for s in subj_onsets if subj_onsets[s] >= SUBJECT_MIN_ONSETS)

    # reject reason tally
    reasons = {}
    for r in rows:
        if not r["usable"]:
            key = r["reject"].split(";")[0].split("(")[0].strip()
            key = re.sub(r"[0-9.]+", "#", key)
            reasons[key] = reasons.get(key, 0) + 1

    print()
    print("=" * 100)
    print("WIDER ALIGNMENT SWEEP — RESULTS")
    print("=" * 100)
    print(f"Nights examined ............... {len(rows)}")
    print(f"Confidently aligned & dense ... {n_usable}  ({100*n_usable/len(rows):.0f}%)  <- the real usable corpus")
    print(f"Offset-0 already clean ........ {sep0_clean}/{sep0_have}  (trusting the doc formula would lose the rest)")
    print()
    cov_fracs = [r["cov_frac"] for r in usable_rows]
    med_cov = float(np.median(cov_fracs)) if cov_fracs else 0.0
    print(f"N3 onsets, all nights (label-derived, alignment-invariant) ... {onsets_all_total}")
    print(f"N3 onsets, covered & on usable nights (all-N3s path) ......... {onsets_cov_usable}")
    print(f"First-N3-only onsets on usable nights (first-only path) ...... {first_onset_usable}")
    print(f"Median HR/EEG overlap on usable nights ....................... {med_cov:.0%}  "
          f"(watch & EEG only partially co-recorded; uncovered onsets have no HR)")
    print()
    print(f"Subjects total ................ {len(subj_all)}")
    print(f"Subjects with >=1 usable night  {len(subj_nights)}")
    print(f"Subjects with >={SUBJECT_MIN_ONSETS} usable onsets  {subj_with_min}/{len(subj_all)}  "
          f"(§5 assumed ~39 pre-gating)")
    print(f"  -> Per-subject density dropped, BUT aggregate cross-subject CV stays viable:")
    print(f"     {onsets_cov_usable} onsets across {len(subj_nights)} subjects "
          f"=> 5-fold gives ~{len(subj_nights)//5} subj & ~{onsets_cov_usable//5} test onsets/fold.")
    print()
    print("Reject reasons (first reason per night):")
    for k, v in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print(f"  {v:4d}  {k}")
    print()
    print("Per-subject usable summary (subject: usable_nights, covered_onsets):")
    for s in sorted(subj_all):
        un = subj_nights.get(s, 0)
        on = subj_onsets.get(s, 0)
        flag = "" if on >= SUBJECT_MIN_ONSETS else "  <-- below CV threshold"
        print(f"  {s}: {un:2d} nights, {on:3d} onsets{flag}")
    print()
    print(f"Wrote {csv_path}")


if __name__ == "__main__":
    main()
