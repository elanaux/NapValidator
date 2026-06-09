#!/usr/bin/env python3
"""Parse NapValidator heart-rate log lines and compute inter-sample intervals.

Input is an ndjson file produced by `log show ... --style ndjson` against a
watchOS logarchive. Only entries whose `eventMessage` matches the
``HR sample t=<unix> bpm=<value>`` pattern emitted by HeartRateMonitor.swift
are kept.

Outputs:
  - A per-sample table (index, ISO timestamp, bpm, delta from previous sample)
  - Aggregate inter-sample interval stats (count, mean, median, p25, p75, min, max)
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from datetime import datetime, timezone

HR_PATTERN = re.compile(r"HR sample t=([0-9.]+) bpm=([0-9.]+)")


def iter_samples(path: str):
    """Yield (unix_seconds: float, bpm: float) for each matching log line."""
    with open(path, "r", encoding="utf-8") as f:
        for line_no, raw in enumerate(f, start=1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                entry = json.loads(raw)
            except json.JSONDecodeError:
                print(f"warn: skipping non-JSON line {line_no}", file=sys.stderr)
                continue
            message = entry.get("eventMessage", "")
            match = HR_PATTERN.search(message)
            if not match:
                continue
            yield float(match.group(1)), float(match.group(2))


def fmt_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(timespec="milliseconds")


def fmt_seconds(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:6.2f}s"
    return f"{seconds / 60:6.2f}m"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("ndjson", help="ndjson file from `log show --style ndjson`")
    parser.add_argument("--no-table", action="store_true",
                        help="suppress per-sample table (only print summary)")
    args = parser.parse_args()

    samples = sorted(iter_samples(args.ndjson), key=lambda s: s[0])
    if not samples:
        print("No HR sample log lines found.", file=sys.stderr)
        return 1

    if not args.no_table:
        print(f"{'#':>4}  {'timestamp (UTC)':<28}  {'bpm':>6}  {'Δ from prev':>11}")
        prev = None
        for i, (ts, bpm) in enumerate(samples):
            delta = "" if prev is None else fmt_seconds(ts - prev)
            print(f"{i:>4}  {fmt_iso(ts):<28}  {bpm:>6.1f}  {delta:>11}")
            prev = ts
        print()

    deltas = [b - a for (a, _), (b, _) in zip(samples, samples[1:])]
    span = samples[-1][0] - samples[0][0]

    print(f"Samples:              {len(samples)}")
    print(f"Session span:         {fmt_seconds(span)}")
    print(f"Inter-sample gaps:    {len(deltas)}")
    if not deltas:
        return 0

    mean = statistics.mean(deltas)
    median = statistics.median(deltas)
    p25 = statistics.quantiles(deltas, n=4)[0] if len(deltas) >= 4 else deltas[0]
    p75 = statistics.quantiles(deltas, n=4)[2] if len(deltas) >= 4 else deltas[-1]

    print(f"  mean:               {fmt_seconds(mean)}")
    print(f"  median:             {fmt_seconds(median)}")
    print(f"  p25 / p75:          {fmt_seconds(p25)} / {fmt_seconds(p75)}")
    print(f"  min / max:          {fmt_seconds(min(deltas))} / {fmt_seconds(max(deltas))}")
    print(f"  effective rate:     {len(samples) / span * 60:.2f} samples/min "
          f"({len(samples) / span * 3600:.1f}/hr)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
