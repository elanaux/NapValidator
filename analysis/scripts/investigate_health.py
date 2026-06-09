#!/usr/bin/env python3
"""Three investigations on the HealthKit export:
A. HRV (SDNN) sampling ceiling — max/day and inter-sample intervals
B. HR sample frequency during sleep windows (proxy for quiet)
C. SleepAnalysis stage content and per-night structure
"""

from __future__ import annotations

import os
import statistics
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from xml.etree.ElementTree import iterparse

PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "apple_health_export", "export.xml",
)

HR_T = "HKQuantityTypeIdentifierHeartRate"
HRV_T = "HKQuantityTypeIdentifierHeartRateVariabilitySDNN"
SLEEP_T = "HKCategoryTypeIdentifierSleepAnalysis"

ASLEEP_VALS = {
    "HKCategoryValueSleepAnalysisAsleepCore",
    "HKCategoryValueSleepAnalysisAsleepDeep",
    "HKCategoryValueSleepAnalysisAsleepREM",
    "HKCategoryValueSleepAnalysisAsleepUnspecified",
}
AWAKE_VAL = "HKCategoryValueSleepAnalysisAwake"
INBED_VAL = "HKCategoryValueSleepAnalysisInBed"

DT_FMT = "%Y-%m-%d %H:%M:%S %z"


def parse_dt(s: str) -> datetime:
    return datetime.strptime(s, DT_FMT)


def strip(v: str) -> str:
    return v.replace("HKCategoryValueSleepAnalysis", "")


def fmt_dur(secs: float) -> str:
    if secs < 60:
        return f"{secs:.1f}s"
    if secs < 3600:
        return f"{secs/60:.1f}m"
    return f"{secs/3600:.2f}h"


def pct(sorted_xs, p):
    if not sorted_xs:
        return 0.0
    k = (len(sorted_xs) - 1) * p / 100
    f = int(k)
    c = min(f + 1, len(sorted_xs) - 1)
    return sorted_xs[f] + (sorted_xs[c] - sorted_xs[f]) * (k - f)


# ----- streaming collection ----------------------------------------------

def collect(path):
    hrv = []      # (dt,)
    hr = []       # (dt, value, source)
    sleep = []    # (start, end, value, source)

    for _, elem in iterparse(path, events=("end",)):
        if elem.tag == "Record":
            t = elem.get("type")
            if t == HR_T:
                sd = elem.get("startDate")
                v = elem.get("value")
                if sd and v:
                    hr.append((parse_dt(sd), float(v), elem.get("sourceName", "")))
            elif t == HRV_T:
                sd = elem.get("startDate")
                if sd:
                    hrv.append(parse_dt(sd))
            elif t == SLEEP_T:
                sd = elem.get("startDate")
                ed = elem.get("endDate")
                if sd and ed:
                    sleep.append((
                        parse_dt(sd), parse_dt(ed),
                        elem.get("value", ""),
                        elem.get("sourceName", ""),
                    ))
        elem.clear()
    return hrv, hr, sleep


# ----- A. HRV ceiling -----------------------------------------------------

def analyze_hrv(hrv):
    print("=" * 72)
    print("A. HRV (SDNN) CEILING")
    print("=" * 72)
    n = len(hrv)
    print(f"Total HRV samples: {n:,}")
    if not n:
        return
    hrv.sort()

    by_day = Counter(dt.date() for dt in hrv)
    top5 = by_day.most_common(5)
    print(f"Days with HRV samples: {len(by_day):,}")
    print(f"Median samples/day: {statistics.median(by_day.values()):.0f}  "
          f"(mean {statistics.mean(by_day.values()):.1f})")
    print(f"\nMax samples in a single day: {top5[0][1]} on {top5[0][0]}")
    print("Top 5 days:")
    for d, c in top5:
        print(f"   {d}   {c:>3} samples")

    # Intra-day gaps only (skip cross-day boundaries — those reflect watch-off, not sampling cadence)
    intra_gaps = []
    same_day_gaps_by_day = defaultdict(list)
    for i in range(1, len(hrv)):
        a, b = hrv[i-1], hrv[i]
        if a.date() == b.date():
            gap = (b - a).total_seconds()
            intra_gaps.append(gap)
            same_day_gaps_by_day[a.date()].append(gap)
    intra_gaps.sort()
    print(f"\nIntra-day inter-sample gaps (n={len(intra_gaps):,}):")
    print(f"  Min:    {intra_gaps[0]:>8.1f}s  ({fmt_dur(intra_gaps[0])})")
    print(f"  p5:     {pct(intra_gaps, 5):>8.1f}s")
    print(f"  p25:    {pct(intra_gaps, 25):>8.1f}s")
    print(f"  Median: {pct(intra_gaps, 50):>8.1f}s  ({fmt_dur(pct(intra_gaps,50))})")
    print(f"  p75:    {pct(intra_gaps, 75):>8.1f}s")
    print(f"  p95:    {pct(intra_gaps, 95):>8.1f}s")
    print(f"  Max:    {intra_gaps[-1]:>8.1f}s  ({fmt_dur(intra_gaps[-1])})")

    # On the heaviest day, show median gap to characterize the upper bound
    top_day = top5[0][0]
    tg = sorted(same_day_gaps_by_day[top_day])
    if tg:
        print(f"\nOn heaviest day ({top_day}): {len(tg)+1} samples, "
              f"median gap {pct(tg,50):.0f}s, min gap {tg[0]:.0f}s")


# ----- B. HR resolution during sustained-low-HR (quiet) windows ----------

HR_THRESHOLD = 70.0       # bpm — anything below counts as "quiet"
MAX_INTERNAL_GAP = 600    # 10 min — split a window if HR samples are this far apart
MIN_WINDOW_SECONDS = 20 * 60


def analyze_hr_quiet(hr):
    print("\n" + "=" * 72)
    print("B. HR SAMPLE FREQUENCY DURING QUIET WINDOWS")
    print("=" * 72)
    print(f"(SleepAnalysis has no stage data and ends 2024-09 — no overlap with HR.")
    print(f" Detecting quiet windows directly: HR < {HR_THRESHOLD:.0f} bpm, ")
    print(f" sample gaps ≤ {MAX_INTERNAL_GAP}s, window ≥ {MIN_WINDOW_SECONDS//60} min.")
    print(f" Apple Watch source only — excludes Bluetooth chest strap.)\n")

    # Filter to Apple Watch and sort
    # (source uses a non-breaking space: "Apple\xa0Watch" — match just "Watch")
    watch = sorted(
        ((dt, v) for dt, v, src in hr if "Watch" in src),
        key=lambda x: x[0],
    )
    print(f"Apple Watch HR samples: {len(watch):,}")

    # Walk samples; build runs of below-threshold readings split on big gaps
    runs = []
    cur = []
    for i, (dt, v) in enumerate(watch):
        if v >= HR_THRESHOLD:
            if cur:
                runs.append(cur)
                cur = []
            continue
        if cur:
            gap = (dt - cur[-1][0]).total_seconds()
            if gap > MAX_INTERNAL_GAP:
                runs.append(cur)
                cur = []
        cur.append((dt, v))
    if cur:
        runs.append(cur)

    # Keep runs spanning ≥ MIN_WINDOW_SECONDS
    windows = [
        r for r in runs
        if (r[-1][0] - r[0][0]).total_seconds() >= MIN_WINDOW_SECONDS
    ]
    total_seconds = sum((r[-1][0] - r[0][0]).total_seconds() for r in windows)
    samples_in = sum(len(r) for r in windows)
    print(f"Quiet windows ≥{MIN_WINDOW_SECONDS//60}min: {len(windows):,} "
          f"({total_seconds/3600:.1f} h total, {samples_in:,} samples)")
    if not windows:
        return

    # Inter-sample gaps inside windows
    gaps = []
    for r in windows:
        for k in range(1, len(r)):
            gaps.append((r[k][0] - r[k-1][0]).total_seconds())
    gaps.sort()

    print(f"\nIntra-window HR inter-sample gaps (n={len(gaps):,}):")
    print(f"  Min:    {gaps[0]:>8.1f}s")
    print(f"  p5:     {pct(gaps, 5):>8.1f}s")
    print(f"  p25:    {pct(gaps, 25):>8.1f}s")
    print(f"  Median: {pct(gaps, 50):>8.1f}s")
    print(f"  Mean:   {statistics.mean(gaps):>8.1f}s")
    print(f"  p75:    {pct(gaps, 75):>8.1f}s")
    print(f"  p95:    {pct(gaps, 95):>8.1f}s")
    print(f"  Max:    {gaps[-1]:>8.1f}s  ({fmt_dur(gaps[-1])})")

    # Effective sampling rate
    print(f"\nEffective rate: {samples_in / (total_seconds/60):.2f} samples/min "
          f"(~1 every {total_seconds/samples_in:.0f}s)")

    # Window-size distribution
    durs = sorted((r[-1][0] - r[0][0]).total_seconds() for r in windows)
    print(f"\nQuiet-window duration: "
          f"median={fmt_dur(pct(durs,50))}, "
          f"p95={fmt_dur(pct(durs,95))}, "
          f"max={fmt_dur(durs[-1])}")


# ----- C. SleepAnalysis content -------------------------------------------

def analyze_sleep(sleep):
    print("\n" + "=" * 72)
    print("C. SLEEP ANALYSIS CONTENT")
    print("=" * 72)
    n = len(sleep)
    print(f"Total records: {n:,}")
    if not n:
        return

    stage_counts = Counter(v for _, _, v, _ in sleep)
    source_counts = Counter(s for _, _, _, s in sleep)
    print("\nDistinct stage values:")
    for v, c in stage_counts.most_common():
        print(f"   {c:>6,}  {strip(v)}")
    print("\nSources:")
    for s, c in source_counts.most_common():
        print(f"   {c:>6,}  {s}")

    dates = sorted({s.date() for s, _, _, _ in sleep})
    print(f"\nDate range: {dates[0]}  →  {dates[-1]}")
    print(f"Distinct dates with records: {len(dates):,}")

    # Per-source record-duration distribution
    print("\nPer-record duration by source (median / p95):")
    by_src = defaultdict(list)
    for s, e, _, src in sleep:
        by_src[src].append((e - s).total_seconds())
    for src, durs in by_src.items():
        d = sorted(durs)
        print(f"   {src:<24}  median={fmt_dur(pct(d,50)):<7}  p95={fmt_dur(pct(d,95)):<7}  "
              f"n={len(d):,}")

    # Per night: group records by night key (start - 12h date) and total InBed time
    nights = defaultdict(list)
    for s, e, v, src in sleep:
        nights[(s - timedelta(hours=12)).date()].append((s, e, v, src))

    # Sample: 8 most-recent nights with ≥2h of InBed
    sampled = []
    for nk in sorted(nights.keys(), reverse=True):
        recs = nights[nk]
        inbed = sum((e - s).total_seconds() for s, e, v, _ in recs
                    if v == INBED_VAL)
        if inbed >= 7200:
            sampled.append((nk, recs, inbed))
        if len(sampled) >= 8:
            break

    print(f"\nSample of {len(sampled)} recent nights with ≥2h InBed:")
    print(f"{'night':<12} {'recs':>5} {'in-bed':>8} {'span':>14}  sources")
    for nk, recs, inbed in sampled:
        starts = [r[0] for r in recs]
        ends = [r[1] for r in recs]
        span = f"{min(starts).strftime('%H:%M')}→{max(ends).strftime('%H:%M')}"
        srcs = ",".join(sorted({r[3] for r in recs}))
        print(f"{str(nk):<12} {len(recs):>5} {fmt_dur(inbed):>8} {span:>14}  {srcs}")


def main():
    print("Streaming export.xml...")
    hrv, hr, sleep = collect(PATH)
    print(f"  HRV samples:   {len(hrv):,}")
    print(f"  HR samples:    {len(hr):,}")
    print(f"  Sleep records: {len(sleep):,}\n")
    analyze_hrv(hrv)
    analyze_hr_quiet(hr)
    analyze_sleep(sleep)


if __name__ == "__main__":
    main()
