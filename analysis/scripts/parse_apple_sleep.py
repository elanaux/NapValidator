#!/usr/bin/env python3
"""Extract Apple Watch sleep-stage data from a HealthKit export.xml.

Streams the export, keeps only HKCategoryTypeIdentifierSleepAnalysis records
written by the Apple Watch, groups them into overnight sessions, and writes
one JSON file describing every session in the requested date window.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import unicodedata
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from xml.etree.ElementTree import iterparse

SLEEP_TYPE = "HKCategoryTypeIdentifierSleepAnalysis"

# HKCategoryValueSleepAnalysis* -> short label used in output
STAGE_MAP = {
    "HKCategoryValueSleepAnalysisInBed": "InBed",
    "HKCategoryValueSleepAnalysisAsleepUnspecified": "AsleepUnspecified",
    "HKCategoryValueSleepAnalysisAsleepCore": "Core",
    "HKCategoryValueSleepAnalysisAsleepDeep": "Deep",
    "HKCategoryValueSleepAnalysisAsleepREM": "REM",
    "HKCategoryValueSleepAnalysisAwake": "Awake",
    # Legacy pre-watchOS 9 value (Apple still emits this on some devices)
    "HKCategoryValueSleepAnalysisAsleep": "AsleepUnspecified",
}
ASLEEP_STAGES = {"Core", "Deep", "REM", "AsleepUnspecified"}

DEFAULT_EXPORT = os.path.expanduser(
    "~/Documents/nap-app/apple_health_export/export.xml"
)
DEFAULT_OUTPUT_DIR = os.path.expanduser("~/Documents/nap-app/apple_sleep")

# Records whose start times are within this many minutes of the running
# session window get folded into the same session. Bridges brief wake gaps.
SESSION_GAP_MINUTES = 60


def parse_apple_date(s: str) -> datetime:
    # Apple's format: "2026-05-14 23:45:00 -0800"
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S %z")


def minutes_between(a: datetime, b: datetime) -> float:
    return (b - a).total_seconds() / 60.0


def merged_total_minutes(intervals: list[tuple[datetime, datetime]]) -> float:
    """Sum duration of intervals, merging any overlaps so time isn't double-counted."""
    if not intervals:
        return 0.0
    sorted_iv = sorted(intervals, key=lambda iv: iv[0])
    total = 0.0
    cur_start, cur_end = sorted_iv[0]
    for s, e in sorted_iv[1:]:
        if s <= cur_end:
            if e > cur_end:
                cur_end = e
        else:
            total += (cur_end - cur_start).total_seconds()
            cur_start, cur_end = s, e
    total += (cur_end - cur_start).total_seconds()
    return total / 60.0


def _normalize(s: str) -> str:
    # NFKC collapses compatibility chars like U+00A0 NO-BREAK SPACE -> ' '.
    # Apple emits "Ellis’s Apple\xa0Watch" with a NBSP between Apple and Watch.
    return unicodedata.normalize("NFKC", s).lower()


def stream_sleep_records(path: str, source_substr: str, cutoff: datetime):
    """Yield dicts for SleepAnalysis records matching the source filter and cutoff."""
    kept = 0
    seen = 0
    needle = _normalize(source_substr)
    context = iterparse(path, events=("end",))
    for _, elem in context:
        if elem.tag == "Record" and elem.get("type") == SLEEP_TYPE:
            seen += 1
            source = elem.get("sourceName", "")
            if needle not in _normalize(source):
                elem.clear()
                continue
            start_raw = elem.get("startDate", "")
            end_raw = elem.get("endDate", "")
            value = elem.get("value", "")
            if not (start_raw and end_raw and value):
                elem.clear()
                continue
            try:
                start = parse_apple_date(start_raw)
                end = parse_apple_date(end_raw)
            except ValueError:
                elem.clear()
                continue
            if end < cutoff:
                elem.clear()
                continue
            kept += 1
            yield {
                "start": start,
                "end": end,
                "stage": STAGE_MAP.get(value, value),
                "raw_value": value,
                "source": source,
            }
        elem.clear()
    print(
        f"  scanned {seen:,} SleepAnalysis records, kept {kept:,} "
        f"matching source '{source_substr}' since {cutoff.isoformat()}",
        file=sys.stderr,
    )


def group_into_sessions(records: list[dict]) -> list[list[dict]]:
    """Sort by start time, then chain records together while gaps stay small."""
    if not records:
        return []
    records.sort(key=lambda r: r["start"])
    sessions: list[list[dict]] = []
    current: list[dict] = [records[0]]
    current_end = records[0]["end"]
    gap = timedelta(minutes=SESSION_GAP_MINUTES)
    for r in records[1:]:
        if r["start"] - current_end <= gap:
            current.append(r)
            if r["end"] > current_end:
                current_end = r["end"]
        else:
            sessions.append(current)
            current = [r]
            current_end = r["end"]
    sessions.append(current)
    return sessions


def summarize_session(records: list[dict]) -> dict:
    session_start = min(r["start"] for r in records)
    session_end = max(r["end"] for r in records)

    # Stage-level records, sorted; InBed kept separate since it's a wrapper.
    stage_records = [r for r in records if r["stage"] != "InBed"]
    in_bed_records = [r for r in records if r["stage"] == "InBed"]
    stage_records.sort(key=lambda r: r["start"])

    transitions = [
        {
            "start": r["start"].isoformat(),
            "end": r["end"].isoformat(),
            "stage": r["stage"],
            "duration_min": round(minutes_between(r["start"], r["end"]), 2),
        }
        for r in stage_records
    ]

    by_stage: dict[str, list[tuple[datetime, datetime]]] = defaultdict(list)
    for r in records:
        by_stage[r["stage"]].append((r["start"], r["end"]))
    totals = {
        stage: round(merged_total_minutes(ivs), 2)
        for stage, ivs in by_stage.items()
    }
    for stage in ("InBed", "Core", "Deep", "REM", "Awake", "AsleepUnspecified"):
        totals.setdefault(stage, 0.0)

    asleep_min = merged_total_minutes(
        [(r["start"], r["end"]) for r in stage_records if r["stage"] in ASLEEP_STAGES]
    )
    if in_bed_records:
        in_bed_min = merged_total_minutes(
            [(r["start"], r["end"]) for r in in_bed_records]
        )
    else:
        in_bed_min = minutes_between(session_start, session_end)
    efficiency = round(asleep_min / in_bed_min * 100, 1) if in_bed_min > 0 else None

    sources = sorted({r["source"] for r in records})

    return {
        "session_start": session_start.isoformat(),
        "session_end": session_end.isoformat(),
        "duration_min": round(minutes_between(session_start, session_end), 2),
        "in_bed_min": round(in_bed_min, 2),
        "asleep_min": round(asleep_min, 2),
        "sleep_efficiency_pct": efficiency,
        "stage_totals_min": totals,
        "stages": transitions,
        "sources": sources,
        "record_count": len(records),
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("path", nargs="?", default=DEFAULT_EXPORT,
                   help=f"Path to export.xml (default: {DEFAULT_EXPORT})")
    p.add_argument("--days", type=int, default=30,
                   help="Window of recent days to keep (default: 30)")
    p.add_argument("--source", default="Apple Watch",
                   help="Case-insensitive sourceName substring filter "
                        "(default: 'Apple Watch')")
    p.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR,
                   help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})")
    args = p.parse_args()

    if not os.path.isfile(args.path):
        print(f"error: export.xml not found at {args.path}", file=sys.stderr)
        sys.exit(1)

    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)
    file_size = os.path.getsize(args.path)
    print(
        f"Parsing {args.path} ({file_size / 1e9:.2f} GB), "
        f"last {args.days} days, source~='{args.source}'..."
    )

    records = list(stream_sleep_records(args.path, args.source, cutoff))
    if not records:
        print("No matching sleep records found. Nothing to write.", file=sys.stderr)
        sys.exit(2)

    sessions = group_into_sessions(records)
    summaries = [summarize_session(s) for s in sessions]

    first_date = min(s["session_start"] for s in summaries)[:10]
    last_date = max(s["session_end"] for s in summaries)[:10]
    os.makedirs(args.output_dir, exist_ok=True)
    out_path = os.path.join(
        args.output_dir, f"apple_sleep_{first_date}_to_{last_date}.json"
    )

    payload = {
        "extracted_at": datetime.now(timezone.utc).isoformat(),
        "export_path": os.path.abspath(args.path),
        "source_filter": args.source,
        "window_days": args.days,
        "date_range": {"start": first_date, "end": last_date},
        "session_count": len(summaries),
        "sessions": summaries,
    }
    with open(out_path, "w") as f:
        json.dump(payload, f, indent=2)

    total_asleep = sum(s["asleep_min"] for s in summaries)
    print(
        f"\nWrote {len(summaries)} sessions ({total_asleep / 60:.1f} h asleep "
        f"total) to {out_path}"
    )


if __name__ == "__main__":
    main()
