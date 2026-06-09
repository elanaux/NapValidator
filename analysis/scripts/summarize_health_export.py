#!/usr/bin/env python3
"""Stream-parse a HealthKit export.xml and print a summary.

Reports:
  - Counts per Record `type` (with overall earliest/latest startDate)
  - Workout count and date range
  - Detailed stats for HeartRate and HeartRateVariabilitySDNN
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from collections import defaultdict
from xml.etree.ElementTree import iterparse

DEFAULT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "apple_health_export",
    "export.xml",
)

HR_TYPE = "HKQuantityTypeIdentifierHeartRate"
HRV_TYPE = "HKQuantityTypeIdentifierHeartRateVariabilitySDNN"


def strip_prefix(rec_type: str) -> str:
    for prefix in ("HKQuantityTypeIdentifier", "HKCategoryTypeIdentifier",
                   "HKDataType", "HKCharacteristicTypeIdentifier"):
        if rec_type.startswith(prefix):
            return rec_type[len(prefix):]
    return rec_type


def fmt_int(n: int) -> str:
    return f"{n:>12,}"


def summarize(path: str) -> None:
    file_size = os.path.getsize(path)
    print(f"Parsing {path} ({file_size / 1e9:.2f} GB)...\n")

    type_counts: dict[str, int] = defaultdict(int)
    type_min_date: dict[str, str] = {}
    type_max_date: dict[str, str] = {}
    source_counts: dict[str, int] = defaultdict(int)

    workout_count = 0
    workout_min: str | None = None
    workout_max: str | None = None
    workout_activities: dict[str, int] = defaultdict(int)

    # Focused stats for HR / HRV
    hr_unit_counts: dict[str, int] = defaultdict(int)
    hrv_unit_counts: dict[str, int] = defaultdict(int)
    hr_source_counts: dict[str, int] = defaultdict(int)
    hrv_source_counts: dict[str, int] = defaultdict(int)

    start = time.time()
    last_report = start
    total_elements = 0

    # iterparse with 'end' events; clear after handling to keep memory flat
    context = iterparse(path, events=("end",))
    for _, elem in context:
        tag = elem.tag
        total_elements += 1

        if tag == "Record":
            rec_type = elem.get("type", "")
            start_date = elem.get("startDate", "")
            source = elem.get("sourceName", "")

            type_counts[rec_type] += 1
            source_counts[source] += 1

            if start_date:
                cur_min = type_min_date.get(rec_type)
                if cur_min is None or start_date < cur_min:
                    type_min_date[rec_type] = start_date
                cur_max = type_max_date.get(rec_type)
                if cur_max is None or start_date > cur_max:
                    type_max_date[rec_type] = start_date

            if rec_type == HR_TYPE:
                hr_unit_counts[elem.get("unit", "")] += 1
                hr_source_counts[source] += 1
            elif rec_type == HRV_TYPE:
                hrv_unit_counts[elem.get("unit", "")] += 1
                hrv_source_counts[source] += 1

        elif tag == "Workout":
            workout_count += 1
            workout_activities[elem.get("workoutActivityType", "")] += 1
            sd = elem.get("startDate", "")
            if sd:
                if workout_min is None or sd < workout_min:
                    workout_min = sd
                if workout_max is None or sd > workout_max:
                    workout_max = sd

        # Free memory: drop the element and any children we've finished with
        elem.clear()

        now = time.time()
        if now - last_report > 5:
            elapsed = now - start
            rate = total_elements / elapsed if elapsed else 0
            print(f"  ... {total_elements:>12,} elements parsed "
                  f"({elapsed:5.1f}s, {rate:,.0f}/s)", file=sys.stderr)
            last_report = now

    elapsed = time.time() - start
    print(f"\nParsed {total_elements:,} elements in {elapsed:.1f}s\n")

    # Overall date range across all records
    all_min = min(type_min_date.values()) if type_min_date else "n/a"
    all_max = max(type_max_date.values()) if type_max_date else "n/a"
    total_records = sum(type_counts.values())

    print("=" * 72)
    print("OVERALL")
    print("=" * 72)
    print(f"Total Record elements: {total_records:,}")
    print(f"Total Workout elements: {workout_count:,}")
    print(f"Date range (records):  {all_min}  ->  {all_max}")
    if workout_count:
        print(f"Date range (workouts): {workout_min}  ->  {workout_max}")

    print("\n" + "=" * 72)
    print(f"RECORD TYPES ({len(type_counts)} distinct)")
    print("=" * 72)
    print(f"{'count':>12}  {'earliest':<26} {'latest':<26} type")
    for rec_type, count in sorted(type_counts.items(), key=lambda kv: -kv[1]):
        print(f"{fmt_int(count)}  "
              f"{type_min_date.get(rec_type, '?'):<26} "
              f"{type_max_date.get(rec_type, '?'):<26} "
              f"{strip_prefix(rec_type)}")

    print("\n" + "=" * 72)
    print(f"SOURCES ({len(source_counts)} distinct, top 15)")
    print("=" * 72)
    for src, count in sorted(source_counts.items(), key=lambda kv: -kv[1])[:15]:
        print(f"{fmt_int(count)}  {src}")

    if workout_activities:
        print("\n" + "=" * 72)
        print("WORKOUT ACTIVITY TYPES")
        print("=" * 72)
        for a, c in sorted(workout_activities.items(), key=lambda kv: -kv[1]):
            print(f"{fmt_int(c)}  {strip_prefix(a)}")

    print("\n" + "=" * 72)
    print("HEART RATE  (HKQuantityTypeIdentifierHeartRate)")
    print("=" * 72)
    hr_count = type_counts.get(HR_TYPE, 0)
    print(f"Samples: {hr_count:,}")
    if hr_count:
        print(f"Range:   {type_min_date[HR_TYPE]}  ->  {type_max_date[HR_TYPE]}")
        print(f"Units:   {dict(hr_unit_counts)}")
        print("Top sources:")
        for src, c in sorted(hr_source_counts.items(), key=lambda kv: -kv[1])[:5]:
            print(f"  {fmt_int(c)}  {src}")

    print("\n" + "=" * 72)
    print("HRV  (HKQuantityTypeIdentifierHeartRateVariabilitySDNN)")
    print("=" * 72)
    hrv_count = type_counts.get(HRV_TYPE, 0)
    print(f"Samples: {hrv_count:,}")
    if hrv_count:
        print(f"Range:   {type_min_date[HRV_TYPE]}  ->  {type_max_date[HRV_TYPE]}")
        print(f"Units:   {dict(hrv_unit_counts)}")
        print("Top sources:")
        for src, c in sorted(hrv_source_counts.items(), key=lambda kv: -kv[1])[:5]:
            print(f"  {fmt_int(c)}  {src}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("path", nargs="?", default=DEFAULT_PATH,
                   help=f"Path to export.xml (default: {DEFAULT_PATH})")
    args = p.parse_args()
    summarize(args.path)


if __name__ == "__main__":
    main()
