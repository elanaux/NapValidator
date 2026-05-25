"""BidSleep dataset fit-verification (read-only, no training).

Walks all Bidslab*/N/{hr.csv,labels.mat} files and answers:

  Q1  HR cadence: rate (samples/min) and median inter-sample gap (s),
      pooled per subject. Reports subject-level distribution.
  Q2  N3 (Deep) corpus size: total N3 epochs, total time, and the
      thing we are actually starved of — number of TRANSITIONS into
      N3 from a non-N3 stage (an N3 "onset"). Counted per night,
      per subject, and globally. Uses expert_label (manual-verified).
  Q3  Structure mapping: HR csv schema, labels.mat schema, epoch
      length, recStart timestamp basis. Already established; cross-
      checked here by comparing recStart to first HR timestamp.

Does NOT train, fit, or modify anything.
"""
from __future__ import annotations

import csv
import glob
import os
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timezone

import numpy as np
from scipy.io import loadmat

ROOT = os.path.dirname(os.path.abspath(__file__))

# Stage code -> name (per dataset doc)
STAGE = {0: "Wake", 1: "N1", 2: "N2", 3: "N3", 4: "REM", 5: "Unknown"}
N3 = 3
EPOCH_S = 30.0

LABEL_FIELD = "expert_label"  # canonical: manual expert annotations


def hr_cadence(path: str) -> tuple[int, float, float, float, float]:
    """Return (n, span_min, rate_per_min, median_gap_s, mean_gap_s)."""
    t = []
    with open(path) as f:
        for row in csv.reader(f):
            if not row:
                continue
            t.append(float(row[0]))
    if len(t) < 2:
        return len(t), 0.0, 0.0, float("inf"), float("inf")
    t.sort()
    arr = np.asarray(t)
    gaps = np.diff(arr)
    span_min = (arr[-1] - arr[0]) / 60.0
    return (
        len(arr),
        float(span_min),
        len(arr) / span_min if span_min > 0 else 0.0,
        float(np.median(gaps)),
        float(gaps.mean()),
    )


def n3_stats(labels: np.ndarray) -> tuple[int, int, int]:
    """Return (n3_epochs, n3_onsets, stage_runs).

    n3_onsets = # times the sequence enters N3 from a non-N3 stage.
    """
    lab = labels.flatten().astype(int)
    if lab.size == 0:
        return 0, 0, 0
    n3_epochs = int(np.sum(lab == N3))
    # transitions into N3
    prev = np.concatenate([[-1], lab[:-1]])
    onsets = int(np.sum((lab == N3) & (prev != N3)))
    # stage-run count
    runs = int(1 + np.sum(lab[1:] != lab[:-1]))
    return n3_epochs, onsets, runs


def main() -> None:
    subjects = sorted(d for d in os.listdir(ROOT) if d.startswith("Bidslab"))
    print(f"Subjects found: {len(subjects)}")

    per_subject_hr = defaultdict(list)   # subj -> list of (rate, med_gap)
    per_subject_n3 = defaultdict(lambda: {"epochs": 0, "onsets": 0, "nights": 0})

    rows = []
    global_n3_epochs = 0
    global_n3_onsets = 0
    global_nights = 0
    global_stage_counts = Counter()
    recstart_vs_hr_offsets = []

    for subj in subjects:
        nights = sorted(
            os.path.basename(d) for d in glob.glob(f"{ROOT}/{subj}/*")
            if os.path.isdir(d)
        )
        for nightdir in nights:
            hr_path = f"{ROOT}/{subj}/{nightdir}/hr.csv"
            lab_path = f"{ROOT}/{subj}/{nightdir}/labels.mat"
            if not (os.path.exists(hr_path) and os.path.exists(lab_path)):
                continue

            n_hr, span_min, rate, med_gap, mean_gap = hr_cadence(hr_path)

            m = loadmat(lab_path)
            labels = m[LABEL_FIELD]
            n3_ep, n3_on, runs = n3_stats(labels)

            # stage distribution (for sanity)
            flat = np.asarray(labels).flatten().astype(int)
            for s, c in Counter(flat).items():
                global_stage_counts[s] += c

            # recStart vs first HR timestamp (cross-check Q3 alignment basis)
            rs = str(m["recStart"][0])
            try:
                # Try UTC first (typical for Unix timestamps)
                rs_dt_utc = datetime.strptime(rs, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                rs_t = rs_dt_utc.timestamp()
                # Read first hr timestamp
                with open(hr_path) as f:
                    first_t = float(next(csv.reader(f))[0])
                recstart_vs_hr_offsets.append(first_t - rs_t)
            except Exception:
                pass

            per_subject_hr[subj].append((rate, med_gap, n_hr, span_min))
            per_subject_n3[subj]["epochs"] += n3_ep
            per_subject_n3[subj]["onsets"] += n3_on
            per_subject_n3[subj]["nights"] += 1
            global_n3_epochs += n3_ep
            global_n3_onsets += n3_on
            global_nights += 1
            rows.append({
                "subject": subj, "night": nightdir,
                "n_hr": n_hr, "span_min": span_min,
                "rate_per_min": rate, "median_gap_s": med_gap,
                "n3_epochs": n3_ep, "n3_onsets": n3_on,
                "n_stage_epochs": int(flat.size),
            })

    # ---- Q1: HR cadence per subject ----
    print()
    print("=" * 96)
    print("Q1  HR cadence per subject  (pooled across that subject's nights)")
    print("=" * 96)
    hdr = f"{'subject':10s} {'nights':6s} {'hr_total':9s} {'rate/min':>9s} {'med_gap_s':>10s} {'mean_gap_s':>11s}"
    print(hdr)
    print("-" * len(hdr))
    all_rates = []
    all_med_gaps = []
    for subj in subjects:
        recs = per_subject_hr.get(subj)
        if not recs:
            continue
        rates = [r for r, _g, _n, _s in recs]
        gaps = [g for _r, g, _n, _s in recs]
        total_hr = sum(n for _r, _g, n, _s in recs)
        mean_gaps = [
            # Skip; we already have median per night. Just average them for a rough subj mean.
            g for _r, g, _n, _s in recs
        ]
        print(f"{subj:10s} {len(recs):6d} {total_hr:9d} {statistics.mean(rates):9.2f} "
              f"{statistics.median(gaps):10.2f} {statistics.mean(mean_gaps):11.2f}")
        all_rates.extend(rates)
        all_med_gaps.extend(gaps)

    print("-" * len(hdr))
    print(f"{'POOLED':10s} {len(rows):6d} "
          f"{sum(r['n_hr'] for r in rows):9d} "
          f"{statistics.mean(all_rates):9.2f} "
          f"{statistics.median(all_med_gaps):10.2f} "
          f"{statistics.mean(all_med_gaps):11.2f}")
    print(f"\nrate/min distribution: min={min(all_rates):.2f}  p25={np.percentile(all_rates,25):.2f}  "
          f"median={np.percentile(all_rates,50):.2f}  p75={np.percentile(all_rates,75):.2f}  max={max(all_rates):.2f}")
    print(f"median-gap distribution: min={min(all_med_gaps):.2f}s  p25={np.percentile(all_med_gaps,25):.2f}s  "
          f"median={np.percentile(all_med_gaps,50):.2f}s  p75={np.percentile(all_med_gaps,75):.2f}s  max={max(all_med_gaps):.2f}s")

    # ---- Q2: N3 corpus size ----
    print()
    print("=" * 96)
    print("Q2  N3 (Deep) corpus  —  the binding constraint")
    print("=" * 96)
    hdr2 = f"{'subject':10s} {'nights':6s} {'N3_epochs':>10s} {'N3_min':>8s} {'N3_onsets':>10s} {'onset/night':>12s}"
    print(hdr2)
    print("-" * len(hdr2))
    for subj in subjects:
        s = per_subject_n3.get(subj)
        if not s or s["nights"] == 0:
            continue
        print(f"{subj:10s} {s['nights']:6d} {s['epochs']:10d} "
              f"{s['epochs']*EPOCH_S/60:8.1f} {s['onsets']:10d} "
              f"{s['onsets']/s['nights']:12.2f}")
    print("-" * len(hdr2))
    print(f"{'TOTAL':10s} {global_nights:6d} {global_n3_epochs:10d} "
          f"{global_n3_epochs*EPOCH_S/60:8.1f} {global_n3_onsets:10d} "
          f"{global_n3_onsets/global_nights:12.2f}")

    print()
    print(f"Global stage-epoch distribution (over {sum(global_stage_counts.values())} 30s epochs):")
    total_ep = sum(global_stage_counts.values())
    for code in sorted(global_stage_counts):
        c = global_stage_counts[code]
        print(f"  {code} ({STAGE.get(code,'?'):7s}): {c:8d}  ({c/total_ep*100:5.1f}%)")

    # ---- Q3: Structure / alignment cross-check ----
    print()
    print("=" * 96)
    print("Q3  Structure & alignment cross-check")
    print("=" * 96)
    print(f"hr.csv : two columns, no header — `unix_timestamp_seconds, bpm`  "
          f"(maps 1:1 to our {{bpm, t}} shape).")
    print(f"labels.mat : keys = recStart (ISO string), expert_label & dreem_label "
          f"(1xN uint8 arrays of stage codes 0=Wake 1=N1 2=N2 3=N3 4=REM 5=Unknown).")
    print(f"Sleep-stage epoch length: {EPOCH_S:.0f} s.")
    print(f"Doc alignment formula: k = floor((t - recStart) / {EPOCH_S:.0f}) + 1")
    if recstart_vs_hr_offsets:
        arr = np.asarray(recstart_vs_hr_offsets)
        print(f"\nrecStart-vs-first-HR offset (assuming recStart parsed as UTC),  n={len(arr)} nights:")
        print(f"  min={arr.min():+.1f}s  p25={np.percentile(arr,25):+.1f}s  "
              f"median={np.percentile(arr,50):+.1f}s  p75={np.percentile(arr,75):+.1f}s  "
              f"max={arr.max():+.1f}s")
        print(f"  mean={arr.mean():+.1f}s  |  abs-median={float(np.median(np.abs(arr))):.1f}s")
        print(f"  (a small consistent offset means recStart is the canonical reference clock; "
              f"a ±3600s or ±7200s spike would mean recStart is local time.)")

    print()
    print("Mapping to our pipeline")
    print("-" * 96)
    print("HR    ->  [{'bpm': bpm, 't': unix_t}, ...]   identical to overnight/*.hr.json")
    print("Stages -> for each night, expand 30s epochs into stage intervals:")
    print("           for k in 0..N-1:")
    print("             start_t = recStart_unix + k*30 ;  end_t = start_t + 30 ;  value = code_to_name(expert_label[k])")
    print("           Apple labels we use are {AsleepCore, AsleepDeep, AsleepREM, Awake};")
    print("           BidSleep AASM map  : 0->Awake, 1+2->AsleepCore (Apple bundles N1+N2),")
    print("                                3->AsleepDeep, 4->AsleepREM, 5->drop or 'Unknown'.")
    print("           Output schema then matches our existing overnight/*.stages.json.")


if __name__ == "__main__":
    main()
