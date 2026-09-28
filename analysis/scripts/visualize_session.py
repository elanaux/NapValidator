"""Visualize a single nap session: HR, motion magnitude, HR variability."""

import json
import sys
from pathlib import Path

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates


SESSIONS_DIR = Path("~/Documents/nap-app/sessions/recovered").expanduser()
OUTPUTS_DIR = Path("~/Documents/nap-app/analysis/outputs").expanduser()
SESSION_FILE = SESSIONS_DIR / "0AF5B9C5-030E-4032-908F-D68CC95DA77E.json"


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


def detect_sleep_onset(t_min, hr_roll_med, motion_t_min, motion_rms, baseline_bpm):
    """First time (min) where rolling-median HR is >=2 bpm below baseline AND
    motion stays below session 25th pctile, both sustained for >=90 s."""
    motion_q25 = np.nanpercentile(motion_rms, 25)
    drop_thresh = baseline_bpm - 2.0
    sustain_min = 1.5

    candidates = np.where((t_min >= 1.0) & (hr_roll_med <= drop_thresh))[0]
    for idx in candidates:
        t0 = t_min[idx]
        window_mask = (t_min >= t0) & (t_min <= t0 + sustain_min)
        if not np.any(window_mask):
            continue
        if np.nanmax(hr_roll_med[window_mask]) > drop_thresh:
            continue
        mw = (motion_t_min >= t0) & (motion_t_min <= t0 + sustain_min)
        if not np.any(mw):
            continue
        if np.nanmedian(motion_rms[mw]) > motion_q25:
            continue
        return t0, hr_roll_med[idx]
    return None, None


def detect_arousal(screen_events, t0, hr_t_min, hr_roll_med, motion_t_min, motion_rms):
    """Find a screen-wake event that coincides with a motion spike (>= 90th pctile)
    within +/- 30 s. Returns (t_min, hr_at_t) or (None, None)."""
    motion_q90 = np.nanpercentile(motion_rms, 90)
    for e in screen_events:
        if e.get("type") != "wake":
            continue
        tm = (e["t"] - t0) / 60.0
        mw = (motion_t_min >= tm - 0.5) & (motion_t_min <= tm + 0.5)
        if not np.any(mw):
            continue
        if np.nanmax(motion_rms[mw]) < motion_q90:
            continue
        hr_idx = int(np.argmin(np.abs(hr_t_min - tm)))
        return tm, hr_roll_med[hr_idx]
    return None, None


def main():
    with open(SESSION_FILE) as f:
        data = json.load(f)

    t0 = data["startTimestamp"]
    t_end = data["endTimestamp"]
    duration_min = (t_end - t0) / 60.0

    # --- HR series ---
    hr = data["heartRateSamples"]
    hr_t = np.array([s["t"] - t0 for s in hr])
    hr_bpm = np.array([s["bpm"] for s in hr], dtype=float)
    hr_t_min = hr_t / 60.0

    hr_roll_med = rolling_apply(hr_t, hr_bpm, 60.0, np.median)
    hr_roll_std = rolling_apply(hr_t, hr_bpm, 60.0, np.std)

    # Waking baseline: median of first 3 minutes of HR
    baseline_mask = hr_t <= 180.0
    baseline_bpm = float(np.median(hr_bpm[baseline_mask])) if baseline_mask.any() else float(np.median(hr_bpm))

    # --- Motion: accel magnitude minus rolling gravity, RMS in 5s bins ---
    motion = data["motionSamples"]
    m_t = np.array([s["t"] - t0 for s in motion])
    ax = np.array([s["ax"] for s in motion])
    ay = np.array([s["ay"] for s in motion])
    az = np.array([s["az"] for s in motion])
    mag = np.sqrt(ax * ax + ay * ay + az * az)
    # 5-second rolling median ~= local gravity vector magnitude; subtract to isolate motion
    grav = rolling_apply(m_t, mag, 5.0, np.median)
    jerk = mag - grav

    bin_s = 5.0
    n_bins = int(np.ceil(m_t[-1] / bin_s))
    bin_centers = (np.arange(n_bins) + 0.5) * bin_s
    bin_idx = np.minimum((m_t // bin_s).astype(int), n_bins - 1)
    motion_rms = np.zeros(n_bins)
    for b in range(n_bins):
        sel = bin_idx == b
        if np.any(sel):
            motion_rms[b] = np.sqrt(np.mean(jerk[sel] ** 2))
    motion_t_min = bin_centers / 60.0

    # --- Sleep onset ---
    onset_min, onset_hr = detect_sleep_onset(
        hr_t_min, hr_roll_med, motion_t_min, motion_rms, baseline_bpm
    )

    # --- Arousal: screen-wake coinciding with motion spike ---
    arousal_min, arousal_hr = detect_arousal(
        data.get("screenEvents", []), t0, hr_t_min, hr_roll_med, motion_t_min, motion_rms
    )

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

    fig, (ax_hr, ax_mot, ax_var) = plt.subplots(
        3, 1, figsize=(13, 9), sharex=True,
        gridspec_kw={"height_ratios": [3, 2, 2], "hspace": 0.15},
    )

    # --- Top: HR ---
    ax_hr.plot(hr_t_min, hr_bpm, color="0.7", linewidth=0.8, marker=".",
               markersize=2.5, label="HR (raw, 0.2 Hz)")
    ax_hr.plot(hr_t_min, hr_roll_med, color="C0", linewidth=1.8,
               label="HR rolling median (60s)")
    ax_hr.axhline(baseline_bpm, color="0.4", linestyle=":", linewidth=1,
                  label=f"Waking baseline ({baseline_bpm:.0f} bpm, first 3 min)")
    ax_hr.set_ylabel("Heart rate (bpm)")
    ax_hr.set_ylim(55, 90)
    ax_hr.legend(loc="upper right", framealpha=0.9, fontsize=8)

    # --- Middle: motion RMS ---
    ax_mot.plot(motion_t_min, motion_rms, color="C1", linewidth=0.9)
    ax_mot.fill_between(motion_t_min, 0, motion_rms, color="C1", alpha=0.2)
    ax_mot.set_yscale("symlog", linthresh=0.005)
    ax_mot.set_ylabel("Motion RMS (g)\n5-s bins, gravity removed")

    # --- Bottom: HR rolling std (variability → deepening proxy) ---
    ax_var.plot(hr_t_min, hr_roll_std, color="C2", linewidth=1.4)
    ax_var.fill_between(hr_t_min, 0, hr_roll_std, color="C2", alpha=0.18)
    ax_var.set_ylabel("HR rolling SD (bpm)\n60-s window")
    ax_var.set_xlabel("Minutes from session start")

    # --- Event overlays on all three axes ---
    screen_events = data.get("screenEvents", [])
    for ax in (ax_hr, ax_mot, ax_var):
        ax.axvline(0, color="black", linewidth=1.0, alpha=0.7)
        ax.axvline(duration_min, color="black", linewidth=1.0, alpha=0.7)
        for e in screen_events:
            if e["type"] == "wake":
                tm = (e["t"] - t0) / 60.0
                ax.axvline(tm, color="C3", linestyle="--", linewidth=0.9, alpha=0.7)

    # Label start, end, and screen-wakes on the top axis only
    y_top = ax_hr.get_ylim()[1]
    ax_hr.text(0, y_top, " start", va="top", ha="left", fontsize=8, color="black")
    ax_hr.text(duration_min, y_top, "end ", va="top", ha="right",
               fontsize=8, color="black")
    for i, e in enumerate(e for e in screen_events if e["type"] == "wake"):
        tm = (e["t"] - t0) / 60.0
        ax_hr.text(tm, y_top, " screen wake", va="top", ha="left",
                   fontsize=8, color="C3", rotation=90)

    # --- Sleep onset annotation (box placed in empty area, leader to marker) ---
    if onset_min is not None:
        for ax in (ax_hr, ax_mot, ax_var):
            ax.axvline(onset_min, color="C4", linewidth=2.0, alpha=0.85)
        ax_hr.annotate(
            f"sleep onset (est.)\nt = {onset_min:.1f} min\nHR ≈ {onset_hr:.0f} bpm",
            xy=(onset_min, onset_hr),
            xytext=(0.18, 0.18), textcoords="axes fraction",
            fontsize=9, color="C4",
            arrowprops=dict(arrowstyle="->", color="C4", lw=1.0,
                            connectionstyle="arc3,rad=-0.2"),
            bbox=dict(boxstyle="round,pad=0.35", fc="white", ec="C4", alpha=0.95),
        )
    else:
        ax_hr.text(0.5, 0.95, "no clear sleep onset detected",
                   transform=ax_hr.transAxes, ha="center", va="top",
                   fontsize=10, color="C4",
                   bbox=dict(boxstyle="round", fc="white", ec="C4"))

    # --- Arousal annotation (motion spike + screen wake + HR drop pattern) ---
    if arousal_min is not None:
        for ax in (ax_hr, ax_mot, ax_var):
            ax.axvline(arousal_min, color="C5", linewidth=2.0, alpha=0.85)
        ax_hr.annotate(
            f"arousal event\nt = {arousal_min:.1f} min\nmotion spike + screen wake",
            xy=(arousal_min, arousal_hr if not np.isnan(arousal_hr) else baseline_bpm),
            xytext=(0.62, 0.22), textcoords="axes fraction",
            fontsize=9, color="C5",
            arrowprops=dict(arrowstyle="->", color="C5", lw=1.0,
                            connectionstyle="arc3,rad=0.2"),
            bbox=dict(boxstyle="round,pad=0.35", fc="white", ec="C5", alpha=0.95),
        )

    # --- Title ---
    short = data["sessionUUID"].split("-")[0]
    fig.suptitle(
        f"Session {short} — {duration_min:.1f} min  ·  "
        f"wake rating: {data.get('wakeRating', '?')}  ·  "
        f"end cause: {data.get('endCause', '?')}",
        fontsize=12, y=0.995,
    )

    ax_var.set_xlim(-1, duration_min + 1)

    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    out = OUTPUTS_DIR / f"{short}_timeline.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    print(f"saved {out}")
    print(f"baseline HR: {baseline_bpm:.1f} bpm")
    if onset_min is not None:
        print(f"sleep onset (est): t+{onset_min:.1f} min, HR ~{onset_hr:.0f} bpm")
    else:
        print("sleep onset: not detected by rule")
    if arousal_min is not None:
        print(f"arousal event:    t+{arousal_min:.1f} min, HR ~{arousal_hr:.0f} bpm")
    else:
        print("arousal event: none detected (no screen-wake + motion-spike coincidence)")


if __name__ == "__main__":
    main()
