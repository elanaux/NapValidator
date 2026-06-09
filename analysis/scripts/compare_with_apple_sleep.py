#!/usr/bin/env python3
"""Compare a NapValidator session to Apple Watch's stage labels for the same window.

Inputs:
  session.json  - one NapValidator session
  apple.json    - apple_sleep_*.json produced by parse_apple_sleep.py

Picks the Apple session with the largest time overlap, clips its stage bands to
the NapValidator window, and stacks four shared-x subplots:
  1. Apple stage band
  2. HR raw + 60s rolling median
  3. Motion RMS (5s bins, gravity-removed, symlog)
  4. HR rolling SD (60s window)

Exits 2 with a message on stderr if no Apple session overlaps.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Patch


SCRIPT_DIR = Path(__file__).resolve().parent
OUTPUTS_DIR = (SCRIPT_DIR / "../outputs").resolve()

STAGE_COLORS = {
    "Core":              "#4A90E2",
    "Deep":              "#1F3A93",
    "REM":               "#8E44AD",
    "Awake":             "#E67E22",
    "InBed":             "#7F8C8D",
    "AsleepUnspecified": "#4A90E2",  # same blue as Core, distinguished by hatch
}
STAGE_HATCH = {"AsleepUnspecified": "///"}
STAGE_LEGEND_ORDER = ["Awake", "REM", "Core", "AsleepUnspecified", "Deep", "InBed"]


def rolling_apply(t, x, window_s, fn):
    """Apply fn over a centered time window for each point in t. O(n) two-pointer."""
    t = np.asarray(t)
    x = np.asarray(x)
    n = len(t)
    out = np.full(n, np.nan)
    half = window_s / 2.0
    lo = 0
    hi = 0
    for i in range(n):
        while lo < n and t[lo] < t[i] - half:
            lo += 1
        while hi < n and t[hi] <= t[i] + half:
            hi += 1
        if hi > lo:
            out[i] = fn(x[lo:hi])
    return out


def iso_to_epoch(s: str) -> float:
    return datetime.fromisoformat(s).timestamp()


def pick_apple_session(nap_start, nap_end, apple_sessions):
    """Return (best_session, best_overlap_seconds, closest_session, closest_gap_seconds)."""
    best = None
    best_overlap = 0.0
    closest = None
    closest_gap = float("inf")
    for s in apple_sessions:
        a_s = iso_to_epoch(s["session_start"])
        a_e = iso_to_epoch(s["session_end"])
        overlap = max(0.0, min(nap_end, a_e) - max(nap_start, a_s))
        if overlap > best_overlap:
            best_overlap = overlap
            best = s
        # Gap = 0 if windows touch or overlap, else distance between them.
        gap = max(0.0, max(nap_start - a_e, a_s - nap_end))
        if gap < closest_gap:
            closest_gap = gap
            closest = s
    return best, best_overlap, closest, closest_gap


def clip_stages(stages, nap_start, duration_min):
    """Clip Apple stage intervals to [0, duration_min]. Returns (bands, clip_stats)."""
    bands = []
    clipped_before = 0.0
    clipped_after = 0.0
    fully_outside = 0
    for st in stages:
        s_min = (iso_to_epoch(st["start"]) - nap_start) / 60.0
        e_min = (iso_to_epoch(st["end"]) - nap_start) / 60.0
        if e_min <= 0 or s_min >= duration_min:
            fully_outside += 1
            continue
        if s_min < 0:
            clipped_before += -s_min
            s_min = 0.0
        if e_min > duration_min:
            clipped_after += e_min - duration_min
            e_min = duration_min
        bands.append((s_min, e_min, st["stage"]))
    return bands, (clipped_before, clipped_after, fully_outside)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("session", help="NapValidator session JSON")
    p.add_argument("apple", help="apple_sleep_*.json from parse_apple_sleep.py")
    args = p.parse_args()

    with open(args.session) as f:
        sess = json.load(f)
    with open(args.apple) as f:
        apple = json.load(f)

    nap_start = sess["startTimestamp"]
    nap_end = sess["endTimestamp"]
    duration_min = (nap_end - nap_start) / 60.0

    best, overlap_s, closest, closest_gap_s = pick_apple_session(
        nap_start, nap_end, apple["sessions"]
    )
    if best is None or overlap_s <= 0:
        msg = "no Apple session overlaps this NapValidator window"
        if closest is not None:
            msg += (
                f" — closest Apple session is {closest['session_start']} "
                f"→ {closest['session_end']} (gap {closest_gap_s / 60:.1f} min)"
            )
        print(msg, file=sys.stderr)
        sys.exit(2)

    bands, (clipped_before, clipped_after, fully_outside) = clip_stages(
        best["stages"], nap_start, duration_min
    )
    if clipped_before or clipped_after or fully_outside:
        print(
            f"clipped Apple stages: {clipped_before:.1f} min before window, "
            f"{clipped_after:.1f} min after window, "
            f"{fully_outside} stages entirely outside",
            file=sys.stderr,
        )

    # --- HR ---
    hr = sess["heartRateSamples"]
    hr_t = np.array([s["t"] - nap_start for s in hr])
    hr_bpm = np.array([s["bpm"] for s in hr], dtype=float)
    hr_t_min = hr_t / 60.0
    hr_roll_med = rolling_apply(hr_t, hr_bpm, 60.0, np.median)
    hr_roll_std = rolling_apply(hr_t, hr_bpm, 60.0, np.std)

    # --- Motion: gravity-removed accel magnitude, RMS in 5s bins ---
    motion = sess["motionSamples"]
    m_t = np.array([s["t"] - nap_start for s in motion])
    ax_a = np.array([s["ax"] for s in motion])
    ay_a = np.array([s["ay"] for s in motion])
    az_a = np.array([s["az"] for s in motion])
    mag = np.sqrt(ax_a * ax_a + ay_a * ay_a + az_a * az_a)
    grav = rolling_apply(m_t, mag, 5.0, np.median)
    jerk = mag - grav
    bin_s = 5.0
    n_bins = int(np.ceil(m_t[-1] / bin_s)) if len(m_t) else 0
    bin_centers = (np.arange(n_bins) + 0.5) * bin_s
    bin_idx = np.minimum((m_t // bin_s).astype(int), max(n_bins - 1, 0))
    motion_rms = np.zeros(n_bins)
    for b in range(n_bins):
        sel = bin_idx == b
        if np.any(sel):
            motion_rms[b] = np.sqrt(np.mean(jerk[sel] ** 2))
    motion_t_min = bin_centers / 60.0

    # --- Plot ---
    plt.rcParams.update({
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.alpha": 0.3,
        "grid.linestyle": "--",
    })

    fig, (ax_apple, ax_hr, ax_mot, ax_var) = plt.subplots(
        4, 1, figsize=(13, 10), sharex=True,
        gridspec_kw={"height_ratios": [1, 3, 2, 2], "hspace": 0.18},
    )

    # --- Top: Apple stage band ---
    present_stages = []
    for s_min, e_min, stage in bands:
        ax_apple.broken_barh(
            [(s_min, e_min - s_min)], (0, 1),
            facecolors=STAGE_COLORS.get(stage, "#555555"),
            edgecolors="white", linewidth=0.5,
            hatch=STAGE_HATCH.get(stage),
        )
        if stage not in present_stages:
            present_stages.append(stage)

    legend_handles = []
    for stage in STAGE_LEGEND_ORDER:
        if stage not in present_stages:
            continue
        label = "AsleepUnspecified (unstaged)" if stage == "AsleepUnspecified" else stage
        legend_handles.append(Patch(
            facecolor=STAGE_COLORS[stage],
            hatch=STAGE_HATCH.get(stage),
            edgecolor="white",
            label=label,
        ))
    if legend_handles:
        ax_apple.legend(
            handles=legend_handles, loc="upper right",
            ncol=len(legend_handles), framealpha=0.9, fontsize=8,
        )
    ax_apple.set_ylim(0, 1)
    ax_apple.set_yticks([])
    ax_apple.set_ylabel("Apple\nstage")
    ax_apple.grid(False)

    # --- HR ---
    ax_hr.plot(hr_t_min, hr_bpm, color="0.7", linewidth=0.8, marker=".",
               markersize=2.5, label="HR (raw)")
    ax_hr.plot(hr_t_min, hr_roll_med, color="C0", linewidth=1.8,
               label="HR rolling median (60s)")
    ax_hr.set_ylabel("Heart rate (bpm)")
    ax_hr.legend(loc="upper right", framealpha=0.9, fontsize=8)

    # --- Motion ---
    ax_mot.plot(motion_t_min, motion_rms, color="C1", linewidth=0.9)
    ax_mot.fill_between(motion_t_min, 0, motion_rms, color="C1", alpha=0.2)
    ax_mot.set_yscale("symlog", linthresh=0.005)
    ax_mot.set_ylabel("Motion RMS (g)\n5-s bins")

    # --- HR rolling SD ---
    ax_var.plot(hr_t_min, hr_roll_std, color="C2", linewidth=1.4)
    ax_var.fill_between(hr_t_min, 0, hr_roll_std, color="C2", alpha=0.18)
    ax_var.set_ylabel("HR rolling SD (bpm)\n60-s window")
    ax_var.set_xlabel("Minutes from NapValidator session start")

    # --- Session-bound and screen-wake markers ---
    screen_wake_mins = [
        (e["t"] - nap_start) / 60.0
        for e in sess.get("screenEvents", [])
        if e.get("type") == "wake"
    ]
    for ax in (ax_apple, ax_hr, ax_mot, ax_var):
        ax.axvline(0, color="black", linewidth=1.0, alpha=0.6)
        ax.axvline(duration_min, color="black", linewidth=1.0, alpha=0.6)
        for tm in screen_wake_mins:
            ax.axvline(tm, color="C3", linestyle="--", linewidth=0.9, alpha=0.7)

    # --- Title ---
    short = sess["sessionUUID"].split("-")[0]
    apple_start_dt = datetime.fromisoformat(best["session_start"])
    apple_total_min = (
        iso_to_epoch(best["session_end"]) - iso_to_epoch(best["session_start"])
    ) / 60.0
    fig.suptitle(
        f"Session {short} — {duration_min:.1f} min  ·  "
        f"wake rating: {sess.get('wakeRating', '—')}  ·  "
        f"end cause: {sess.get('endCause', '?')}\n"
        f"matched Apple session starting {apple_start_dt.strftime('%Y-%m-%d %H:%M')} "
        f"({overlap_s / 60:.1f} min overlap of {apple_total_min:.0f} min total)",
        fontsize=11, y=0.995,
    )

    ax_var.set_xlim(-1, duration_min + 1)

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUTS_DIR / f"{short}_apple_comparison.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"saved {out}")
    print(f"matched Apple session: {best['session_start']} -> {best['session_end']}")
    print(f"overlap: {overlap_s / 60:.1f} min  ·  Apple stages drawn: {len(bands)}")


if __name__ == "__main__":
    main()
