"""Shape-hypothesis analysis on two real overnights.

Inputs (recovered files):
  ~/Desktop/nap-app/sessions_recovered/overnight/{2026-05-17_AB2FFBAD,2026-05-20_8C86E7F9}.{hr,stages}.json

Q1: Rolling-60s HR-SD distribution in scored AsleepDeep vs AsleepCore.
    Key number: fraction of in-Deep rolling windows with SD < 0.8 (t_var).
Q2: Lag between steepest HR-level decline and steepest SD-compression at Deep onset.
    Negative = SD leads HR.
Q3: 60s vs 90s vs 120s sustain windows inside Deep — sub-minute SD reset rate.
Q4: Replay the dual (HR <= ref-5) AND (SD<0.8) sustained-60s trigger; check fires
    inside Apple-labeled Deep stretches and false fires elsewhere.

Saves plots to ~/Desktop/nap-app/analysis_shape_hypothesis/
"""
from __future__ import annotations

import json
import os
from collections import Counter

import matplotlib.pyplot as plt
import numpy as np

OVERNIGHT_DIR = os.path.expanduser("~/Desktop/nap-app/sessions_recovered/overnight")
OUT_DIR = os.path.expanduser("~/Desktop/nap-app/analysis_shape_hypothesis")
os.makedirs(OUT_DIR, exist_ok=True)

SESSIONS = [
    ("AB2FFBAD", "2026-05-17_AB2FFBAD", "May 17"),
    ("8C86E7F9", "2026-05-20_8C86E7F9", "May 20"),
]

T_HR_DROP = 5.0
T_VAR = 0.8
D_SUSTAIN = 60.0
WINDOW_SD = 60.0   # rolling SD window (s)
TRANS_HALF = 180.0  # ±180s around Deep onset for Q2

# HR-density gate. Rolling-60s SD needs multiple samples per minute to be
# meaningful. Below threshold, every rolling window is all-NaN; the 1Hz
# interp path then fills NaN with nanmean (which is 0.0 when *all* values
# are NaN), making every Deep window trivially satisfy SD<T_VAR. The gate
# blocks that silent artifact and explicitly returns INSUFFICIENT-HR-DENSITY.
MIN_HR_PER_MIN = 4.0
MAX_MEDIAN_GAP_S = 15.0


# ---------- I/O ----------

def load_session(base: str):
    hr = json.load(open(f"{OVERNIGHT_DIR}/{base}.hr.json"))
    st = json.load(open(f"{OVERNIGHT_DIR}/{base}.stages.json"))
    t = np.array([s["t"] for s in hr], dtype=float)
    bpm = np.array([s["bpm"] for s in hr], dtype=float)
    order = np.argsort(t)
    t = t[order]
    bpm = bpm[order]
    return t, bpm, st


def merged_stretches(stages: list[dict], value: str, gap_tol: float = 1.0) -> list[tuple[float, float]]:
    """Merge contiguous same-value stage records (Apple emits adjacent splits)."""
    recs = sorted([s for s in stages if s["value"] == value], key=lambda r: r["start_t"])
    if not recs:
        return []
    out = [[recs[0]["start_t"], recs[0]["end_t"]]]
    for r in recs[1:]:
        if r["start_t"] - out[-1][1] <= gap_tol:
            out[-1][1] = max(out[-1][1], r["end_t"])
        else:
            out.append([r["start_t"], r["end_t"]])
    return [(a, b) for a, b in out]


def all_merged(stages, gap_tol: float = 1.0) -> list[tuple[float, float, str]]:
    recs = sorted(stages, key=lambda r: r["start_t"])
    out = []
    for r in recs:
        if out and r["value"] == out[-1][2] and r["start_t"] - out[-1][1] <= gap_tol:
            out[-1][1] = max(out[-1][1], r["end_t"])
        else:
            out.append([r["start_t"], r["end_t"], r["value"]])
    return [(a, b, v) for a, b, v in out]


# ---------- Rolling SD over irregular HR series ----------

def rolling_sd_trailing(t: np.ndarray, bpm: np.ndarray, window: float = WINDOW_SD) -> np.ndarray:
    """SD of bpm samples in (t[i]-window, t[i]]; NaN if <2 samples in window."""
    n = len(t)
    out = np.full(n, np.nan)
    j = 0
    for i in range(n):
        while t[j] < t[i] - window:
            j += 1
        if i - j + 1 >= 2:
            out[i] = np.std(bpm[j:i + 1], ddof=1)
    return out


def percentiles_of(x: np.ndarray) -> dict:
    x = x[~np.isnan(x)]
    if x.size == 0:
        return {"n": 0}
    return {
        "n": int(x.size),
        "min": float(x.min()),
        "p5": float(np.percentile(x, 5)),
        "p25": float(np.percentile(x, 25)),
        "p50": float(np.percentile(x, 50)),
        "p75": float(np.percentile(x, 75)),
        "p95": float(np.percentile(x, 95)),
        "max": float(x.max()),
        "mean": float(x.mean()),
    }


# ---------- Q1: SD distribution in Deep vs Core ----------

def mask_in_intervals(t: np.ndarray, intervals: list[tuple[float, float]]) -> np.ndarray:
    m = np.zeros(t.shape, dtype=bool)
    for a, b in intervals:
        m |= (t >= a) & (t <= b)
    return m


# ---------- Helpers: 1Hz interpolation of HR + SD ----------

def make_1hz(t: np.ndarray, bpm: np.ndarray, sd: np.ndarray):
    t_min, t_max = t[0], t[-1]
    grid = np.arange(np.ceil(t_min), np.floor(t_max) + 1.0)
    # Linear interp HR. SD: forward-fill semantics (only defined after window fills).
    bpm_g = np.interp(grid, t, bpm)
    sd_g = np.interp(grid, t, np.where(np.isnan(sd), np.nanmean(sd[~np.isnan(sd)]) if np.any(~np.isnan(sd)) else 0.0, sd))
    return grid, bpm_g, sd_g


def smooth(x: np.ndarray, w: int = 15) -> np.ndarray:
    """Boxcar smoothing (length w samples)."""
    if w <= 1:
        return x.copy()
    pad = w // 2
    xp = np.pad(x, pad, mode="edge")
    k = np.ones(w) / w
    return np.convolve(xp, k, mode="valid")[: x.size]


def derivative(x: np.ndarray) -> np.ndarray:
    return np.gradient(x)


# ---------- HR-density gate ----------

def hr_density(t: np.ndarray) -> dict:
    if len(t) < 2:
        return {"n": int(len(t)), "rate_per_min": 0.0,
                "median_gap_s": float("inf"), "p25_gap_s": float("inf"),
                "p75_gap_s": float("inf")}
    span_min = (t[-1] - t[0]) / 60.0
    gaps = np.diff(t)
    return {
        "n": int(len(t)),
        "rate_per_min": float(len(t) / span_min) if span_min > 0 else 0.0,
        "median_gap_s": float(np.median(gaps)),
        "p25_gap_s": float(np.percentile(gaps, 25)),
        "p75_gap_s": float(np.percentile(gaps, 75)),
    }


def density_sufficient(d: dict) -> tuple[bool, str]:
    if d["rate_per_min"] < MIN_HR_PER_MIN:
        return False, f"rate {d['rate_per_min']:.2f}/min < {MIN_HR_PER_MIN:.1f}/min required"
    if d["median_gap_s"] > MAX_MEDIAN_GAP_S:
        return False, f"median gap {d['median_gap_s']:.1f}s > {MAX_MEDIAN_GAP_S:.0f}s required"
    return True, ""


# ---------- Q2: Lag at Deep onset ----------

def transition_indices(stages_merged: list[tuple[float, float, str]]) -> list[float]:
    """Onsets of Deep stretches that follow a non-Deep stretch."""
    out = []
    prev_value = None
    for a, b, v in stages_merged:
        if v == "AsleepDeep" and prev_value != "AsleepDeep":
            out.append(a)
        prev_value = v
    return out


# ---------- Q3: Sustain-window comparison ----------

def sustained_low_episodes(t_grid: np.ndarray, sd_grid: np.ndarray, deep_intervals, sustain_s: float, thr: float = T_VAR):
    """Count maximal contiguous spans on the 1Hz grid where sd<thr for >= sustain_s,
    restricted to inside Deep intervals."""
    in_deep = mask_in_intervals(t_grid, deep_intervals)
    cond = (sd_grid < thr) & in_deep
    # find runs of True
    episodes = []
    i = 0
    n = len(cond)
    while i < n:
        if not cond[i]:
            i += 1
            continue
        j = i
        while j < n and cond[j]:
            j += 1
        dur = j - i  # samples at 1Hz = seconds
        if dur >= sustain_s:
            episodes.append((t_grid[i], t_grid[j - 1], dur))
        i = j
    return episodes


def crossings_above_then_below(t_grid: np.ndarray, sd_grid: np.ndarray, deep_intervals, thr: float = T_VAR, span: float = 60.0):
    """Count up-and-back-down round trips within `span` seconds while inside Deep."""
    in_deep = mask_in_intervals(t_grid, deep_intervals)
    above = sd_grid >= thr
    # transitions
    diff = np.diff(above.astype(int))
    up_idx = np.where(diff == 1)[0] + 1   # crossing up (now above)
    down_idx = np.where(diff == -1)[0] + 1  # crossing down (now below)
    round_trips = 0
    for u in up_idx:
        if not in_deep[u]:
            continue
        # find next down after u
        cands = down_idx[down_idx > u]
        if cands.size == 0:
            continue
        d = cands[0]
        if t_grid[d] - t_grid[u] <= span and in_deep[d]:
            round_trips += 1
    return round_trips, len(up_idx), len(down_idx)


# ---------- Q4: trigger replay ----------

def light_reference_hr(t: np.ndarray, bpm: np.ndarray, core_intervals, min_dur: float = 300.0) -> tuple[float, tuple[float, float]]:
    """Median HR over the first Core stretch >= min_dur seconds."""
    for a, b in core_intervals:
        if b - a >= min_dur:
            m = (t >= a) & (t <= b)
            if m.sum() > 0:
                return float(np.median(bpm[m])), (a, b)
    # fall back to first Core
    if core_intervals:
        a, b = core_intervals[0]
        m = (t >= a) & (t <= b)
        return float(np.median(bpm[m])), (a, b)
    return float(np.median(bpm)), (t[0], t[-1])


def replay_trigger(t_grid, bpm_grid, sd_grid, hr_thr, sustain_s=D_SUSTAIN, var_thr=T_VAR):
    cond = (bpm_grid <= hr_thr) & (sd_grid < var_thr)
    fires = []  # list of (fire_time, run_start, run_end)
    i = 0
    n = len(cond)
    while i < n:
        if not cond[i]:
            i += 1
            continue
        j = i
        while j < n and cond[j]:
            j += 1
        run_dur = j - i
        if run_dur >= sustain_s:
            fires.append((t_grid[i + int(sustain_s) - 1], t_grid[i], t_grid[j - 1]))
        i = j
    return fires


# =================================================================
#                              MAIN
# =================================================================

def analyse_session(short, base, label):
    print(f"\n>>> session {short} ({label}) <<<")
    t, bpm, stages = load_session(base)
    merged = all_merged(stages)
    deep_iv = merged_stretches(stages, "AsleepDeep")
    core_iv = merged_stretches(stages, "AsleepCore")
    rem_iv  = merged_stretches(stages, "AsleepREM")

    print(f"  HR samples: {len(t)};  Deep stretches: {len(deep_iv)}  Core: {len(core_iv)}  REM: {len(rem_iv)}")
    deep_tot_min = sum(b - a for a, b in deep_iv) / 60.0
    core_tot_min = sum(b - a for a, b in core_iv) / 60.0
    print(f"  total Deep: {deep_tot_min:.1f} min;  total Core: {core_tot_min:.1f} min")

    # ---- HR-density gate (precedes any rolling-60s-SD computation) ----
    density = hr_density(t)
    ok, gate_reason = density_sufficient(density)
    print(f"  HR density : {density['rate_per_min']:.2f}/min   "
          f"median inter-sample gap {density['median_gap_s']:.1f}s "
          f"(p25={density['p25_gap_s']:.1f}s, p75={density['p75_gap_s']:.1f}s)")
    if not ok:
        print(f"  !! INSUFFICIENT-HR-DENSITY: {gate_reason}")
        print(f"     Q1/Q2/Q3/Q4 SKIPPED — rolling-60s SD cannot be computed reliably.")
        return {
            "short": short, "base": base, "label": label,
            "t": t, "bpm": bpm, "sd": np.array([]),
            "merged": merged, "deep_iv": deep_iv, "core_iv": core_iv,
            "deep_sd": np.array([]), "core_sd": np.array([]),
            "p_deep": {"n": 0}, "p_core": {"n": 0},
            "frac_deep_lt_tvar": float("nan"),
            "frac_core_lt_tvar": float("nan"),
            "deep_onsets": transition_indices(all_merged(stages)),
            "lags": [], "overlays_hr": [], "overlays_sd": [],
            "sub60_round_trips": 0,
            "ep60": [], "ep90": [], "ep120": [],
            "ref_hr": float("nan"),
            "ref_iv": (float("nan"), float("nan")),
            "hr_thr": float("nan"),
            "fires": [], "fires_in_deep": [], "fires_out_deep": [],
            "deep_fires_per_stretch": [],
            "deep_tot_min": deep_tot_min, "core_tot_min": core_tot_min,
            "t_grid": np.array([]), "bpm_grid": np.array([]),
            "sd_grid": np.array([]),
            "density": density, "gated": True, "gate_reason": gate_reason,
        }

    sd = rolling_sd_trailing(t, bpm, WINDOW_SD)

    # ---- Q1 ----
    in_deep = mask_in_intervals(t, deep_iv)
    in_core = mask_in_intervals(t, core_iv)
    deep_sd = sd[in_deep]
    core_sd = sd[in_core]
    deep_sd = deep_sd[~np.isnan(deep_sd)]
    core_sd = core_sd[~np.isnan(core_sd)]
    p_deep = percentiles_of(deep_sd)
    p_core = percentiles_of(core_sd)
    frac_deep_lt_tvar = float(np.mean(deep_sd < T_VAR)) if deep_sd.size else float("nan")
    frac_core_lt_tvar = float(np.mean(core_sd < T_VAR)) if core_sd.size else float("nan")

    # ---- Q2 ----
    deep_onsets = transition_indices(merged)
    t_grid, bpm_grid, sd_grid = make_1hz(t, bpm, sd)
    bpm_s = smooth(bpm_grid, 15)
    sd_s  = smooth(sd_grid, 15)
    dbpm = derivative(bpm_s)
    dsd  = derivative(sd_s)

    lags = []
    overlays_hr = []
    overlays_sd = []
    for t0 in deep_onsets:
        # window indices on the 1Hz grid
        a = int(np.searchsorted(t_grid, t0 - TRANS_HALF, side="left"))
        b = int(np.searchsorted(t_grid, t0 + TRANS_HALF, side="right"))
        if b - a < int(2 * TRANS_HALF * 0.7):
            continue  # incomplete window (near session edge)
        rel = t_grid[a:b] - t0
        hr_w = bpm_s[a:b]
        sd_w = sd_s[a:b]
        dhr_w = dbpm[a:b]
        dsd_w = dsd[a:b]
        i_hr = int(np.argmin(dhr_w))
        i_sd = int(np.argmin(dsd_w))
        t_hr_min = float(rel[i_hr])
        t_sd_min = float(rel[i_sd])
        lag = t_sd_min - t_hr_min
        lags.append({"t0": t0, "t_hr_inflect": t_hr_min, "t_sd_inflect": t_sd_min, "lag": lag})

        # z-normalize for overlay
        def z(x):
            mu, sd_x = np.nanmean(x), np.nanstd(x)
            return (x - mu) / sd_x if sd_x > 0 else x - mu
        # Resample to fixed grid -TRANS_HALF..+TRANS_HALF, step 1s
        fixed = np.arange(-TRANS_HALF, TRANS_HALF + 1)
        hr_fx = np.interp(fixed, rel, hr_w)
        sd_fx = np.interp(fixed, rel, sd_w)
        overlays_hr.append(z(hr_fx))
        overlays_sd.append(z(sd_fx))

    # ---- Q3 ----
    sub60_round_trips, _, _ = crossings_above_then_below(t_grid, sd_grid, deep_iv, thr=T_VAR, span=60.0)
    ep60  = sustained_low_episodes(t_grid, sd_grid, deep_iv, sustain_s=60.0)
    ep90  = sustained_low_episodes(t_grid, sd_grid, deep_iv, sustain_s=90.0)
    ep120 = sustained_low_episodes(t_grid, sd_grid, deep_iv, sustain_s=120.0)

    # ---- Q4 ----
    ref_hr, ref_iv = light_reference_hr(t, bpm, core_iv)
    hr_thr = ref_hr - T_HR_DROP
    fires = replay_trigger(t_grid, bpm_grid, sd_grid, hr_thr)
    # classify each fire
    fires_in_deep = []
    fires_out_deep = []
    for fire_t, run_a, run_b in fires:
        in_dp = any(a <= fire_t <= b for a, b in deep_iv)
        if in_dp:
            # find which Deep stretch and offset from its onset
            for a, b in deep_iv:
                if a <= fire_t <= b:
                    fires_in_deep.append((fire_t, run_a, run_b, fire_t - a))
                    break
        else:
            fires_out_deep.append((fire_t, run_a, run_b))
    # per Deep stretch: did trigger ever fire inside?
    deep_fires_per_stretch = []
    for a, b in deep_iv:
        firing = [(fa, ra, rb) for (fa, ra, rb) in fires if a <= fa <= b]
        deep_fires_per_stretch.append({
            "stretch": (a, b),
            "dur_s": b - a,
            "first_fire_offset": (firing[0][0] - a) if firing else None,
            "n_fires": len(firing),
        })

    return {
        "short": short, "base": base, "label": label,
        "t": t, "bpm": bpm, "sd": sd,
        "merged": merged, "deep_iv": deep_iv, "core_iv": core_iv,
        "deep_sd": deep_sd, "core_sd": core_sd,
        "p_deep": p_deep, "p_core": p_core,
        "frac_deep_lt_tvar": frac_deep_lt_tvar,
        "frac_core_lt_tvar": frac_core_lt_tvar,
        "deep_onsets": deep_onsets, "lags": lags,
        "overlays_hr": overlays_hr, "overlays_sd": overlays_sd,
        "sub60_round_trips": sub60_round_trips,
        "ep60": ep60, "ep90": ep90, "ep120": ep120,
        "ref_hr": ref_hr, "ref_iv": ref_iv, "hr_thr": hr_thr,
        "fires": fires, "fires_in_deep": fires_in_deep, "fires_out_deep": fires_out_deep,
        "deep_fires_per_stretch": deep_fires_per_stretch,
        "deep_tot_min": deep_tot_min, "core_tot_min": core_tot_min,
        "t_grid": t_grid, "bpm_grid": bpm_grid, "sd_grid": sd_grid,
        "density": density, "gated": False, "gate_reason": "",
    }


def print_session_headline(r: dict) -> None:
    """Print the Q1-Q4 one-liners for a single session result dict.

    Used by callers that want a per-session summary (e.g. daily morning pull).
    Stage architecture, density, and any gate message are printed by
    analyse_session() itself; this function adds the four-question lines and
    is a no-op when the session was gated for insufficient HR density.
    """
    if r.get("gated"):
        return
    p_deep = r["p_deep"]
    p_core = r["p_core"]
    print(f"  Q1  Deep rolling-SD median = {p_deep.get('p50', float('nan')):.3f} bpm "
          f"(p25={p_deep.get('p25', float('nan')):.3f}, p75={p_deep.get('p75', float('nan')):.3f})   "
          f"Core median = {p_core.get('p50', float('nan')):.3f} bpm")
    print(f"      fraction of in-Deep windows w/ SD < {T_VAR}: "
          f"{r['frac_deep_lt_tvar']*100:.1f}%   (in-Core: {r['frac_core_lt_tvar']*100:.1f}%)")
    lags = [L["lag"] for L in r["lags"]]
    if lags:
        n_neg = sum(1 for x in lags if x < 0)
        print(f"  Q2  Lag (SD-inflect - HR-inflect) over {len(lags)} Deep onsets: "
              f"mean={float(np.mean(lags)):+.1f}s  median={float(np.median(lags)):+.1f}s  "
              f"SD-leads in {n_neg}/{len(lags)}")
    else:
        print(f"  Q2  No full-window Deep onsets in this session (deep_onsets={len(r['deep_onsets'])})")
    print(f"  Q3  Sustained low-SD episodes inside Deep (SD<{T_VAR}, sustain>=W): "
          f"W=60s -> {len(r['ep60'])}   W=90s -> {len(r['ep90'])}   W=120s -> {len(r['ep120'])}")
    if not np.isnan(r["ref_hr"]):
        n_deep_with_fire = sum(1 for d in r["deep_fires_per_stretch"] if d["n_fires"] > 0)
        print(f"  Q4  Light-ref HR = {r['ref_hr']:.1f} bpm, HR thr = {r['hr_thr']:.1f}   "
              f"fires total={len(r['fires'])}  in-Deep={len(r['fires_in_deep'])}  "
              f"out-Deep={len(r['fires_out_deep'])}   "
              f"Deep stretches with >=1 fire: {n_deep_with_fire}/{len(r['deep_iv'])}")
    else:
        print(f"  Q4  No Core stretch / no HR grid — trigger replay skipped")


def main():
    results = [analyse_session(short, base, label) for short, base, label in SESSIONS]
    dense = [r for r in results if not r.get("gated")]
    gated = [r for r in results if r.get("gated")]

    # ===== Headline summary table =====
    print()
    print("=" * 110)
    print(f"SHAPE-HYPOTHESIS HEADLINE SUMMARY  "
          f"(n={len(dense)} dense, {len(gated)} gated for insufficient HR density)")
    print("=" * 110)
    print()

    if gated:
        print("Sessions GATED — Q1/Q2/Q3/Q4 unavailable on these (HR density too low):")
        for r in gated:
            d = r["density"]
            print(f"  {r['short']} ({r['label']}): rate {d['rate_per_min']:.2f}/min, "
                  f"median gap {d['median_gap_s']:.1f}s  — {r['gate_reason']}")
        print()

    # Pool Q1 across DENSE sessions only
    deep_pool = np.concatenate([r["deep_sd"] for r in dense]) if dense else np.array([])
    core_pool = np.concatenate([r["core_sd"] for r in dense]) if dense else np.array([])
    pp_deep = percentiles_of(deep_pool)
    pp_core = percentiles_of(core_pool)
    frac_deep_pool = float(np.mean(deep_pool < T_VAR)) if deep_pool.size else float("nan")

    # Q2 pooled lag (dense only)
    lags_pool = [L["lag"] for r in dense for L in r["lags"]]
    mean_lag = float(np.mean(lags_pool)) if lags_pool else float("nan")
    median_lag = float(np.median(lags_pool)) if lags_pool else float("nan")
    n_neg = sum(1 for x in lags_pool if x < 0)

    # Q3 pooled (dense only)
    n60  = sum(len(r["ep60"]) for r in dense)
    n90  = sum(len(r["ep90"]) for r in dense)
    n120 = sum(len(r["ep120"]) for r in dense)

    # Q4 pooled (dense only)
    n_fires_total = sum(len(r["fires"]) for r in dense)
    n_fires_in = sum(len(r["fires_in_deep"]) for r in dense)
    n_fires_out = sum(len(r["fires_out_deep"]) for r in dense)
    n_deep_stretches = sum(len(r["deep_iv"]) for r in dense)
    n_deep_with_fire = sum(1 for r in dense for d in r["deep_fires_per_stretch"] if d["n_fires"] > 0)

    print(f"  Q1  Deep rolling-SD median (pooled)   : {pp_deep.get('p50', float('nan')):.3f} bpm  "
          f"(p25={pp_deep.get('p25', float('nan')):.3f}, p75={pp_deep.get('p75', float('nan')):.3f}) "
          f"vs Core median {pp_core.get('p50', float('nan')):.3f} bpm")
    print(f"      Fraction of in-Deep windows w/ SD < {T_VAR}: {frac_deep_pool*100:.1f}%   "
          f"(in-Core: {float(np.mean(core_pool < T_VAR))*100:.1f}%)")
    print()
    print(f"  Q2  Lag (SD-inflect − HR-inflect) at Deep onset, n={len(lags_pool)} transitions: "
          f"mean={mean_lag:+.1f}s, median={median_lag:+.1f}s, "
          f"negative-lag (SD leads HR) in {n_neg}/{len(lags_pool)}")
    print()
    print(f"  Q3  Sustained-low-SD episodes inside Deep "
          f"(SD<{T_VAR} held for >=W): W=60s -> {n60}   W=90s -> {n90}   W=120s -> {n120}")
    print()
    print(f"  Q4  Dual-trigger replay (HR<=ref-5 AND SD<{T_VAR}, sustain>={int(D_SUSTAIN)}s):")
    print(f"      Total fires: {n_fires_total}   inside scored-Deep: {n_fires_in}   "
          f"outside Deep (false): {n_fires_out}")
    print(f"      Deep stretches that received >=1 fire: {n_deep_with_fire}/{n_deep_stretches}")
    print()
    print("=" * 110)

    # ===== Per-question detail =====
    print()
    print("--- Q1 detail: rolling 60s HR-SD percentiles ---")
    hdr = f"{'session':10s} {'phase':6s} {'n':>5s} {'min':>6s} {'p5':>6s} {'p25':>6s} {'p50':>6s} {'p75':>6s} {'p95':>6s} {'max':>6s} {'mean':>6s} {'frac<'+str(T_VAR):>9s}"
    print(hdr)
    print("-" * len(hdr))
    for r in results:
        if r.get("gated"):
            print(f"{r['short']:10s} {'-':6s} INSUFFICIENT-HR-DENSITY ({r['gate_reason']})")
            continue
        for phase, parr in (("Deep", r["deep_sd"]), ("Core", r["core_sd"])):
            p = percentiles_of(parr)
            frac = float(np.mean(parr < T_VAR)) if parr.size else float("nan")
            print(f"{r['short']:10s} {phase:6s} {p.get('n',0):5d} "
                  f"{p.get('min', float('nan')):6.2f} {p.get('p5', float('nan')):6.2f} {p.get('p25', float('nan')):6.2f} "
                  f"{p.get('p50', float('nan')):6.2f} {p.get('p75', float('nan')):6.2f} {p.get('p95', float('nan')):6.2f} "
                  f"{p.get('max', float('nan')):6.2f} {p.get('mean', float('nan')):6.2f} {frac*100:8.1f}%")
    if dense:
        print(f"{'POOLED':10s} {'Deep':6s} {pp_deep['n']:5d} {pp_deep['min']:6.2f} {pp_deep['p5']:6.2f} {pp_deep['p25']:6.2f} "
              f"{pp_deep['p50']:6.2f} {pp_deep['p75']:6.2f} {pp_deep['p95']:6.2f} {pp_deep['max']:6.2f} {pp_deep['mean']:6.2f} "
              f"{frac_deep_pool*100:8.1f}%")
        print(f"{'POOLED':10s} {'Core':6s} {pp_core['n']:5d} {pp_core['min']:6.2f} {pp_core['p5']:6.2f} {pp_core['p25']:6.2f} "
              f"{pp_core['p50']:6.2f} {pp_core['p75']:6.2f} {pp_core['p95']:6.2f} {pp_core['max']:6.2f} {pp_core['mean']:6.2f} "
              f"{float(np.mean(core_pool < T_VAR))*100:8.1f}%")
    else:
        print("  (no dense sessions — POOLED row unavailable)")

    print()
    print("--- Q2 detail: per-transition lag ---")
    for r in results:
        if r.get("gated"):
            print(f"  {r['short']}: INSUFFICIENT-HR-DENSITY ({r['gate_reason']})")
            continue
        print(f"  {r['short']} (Deep onsets n={len(r['lags'])}):")
        for L in r["lags"]:
            print(f"    t_HR_inflect={L['t_hr_inflect']:+6.1f}s   t_SD_inflect={L['t_sd_inflect']:+6.1f}s   "
                  f"lag={L['lag']:+6.1f}s  ({'SD-leads' if L['lag']<0 else 'HR-leads' if L['lag']>0 else 'simultaneous'})")

    print()
    print("--- Q3 detail: sustain-window comparison inside Deep ---")
    for r in results:
        if r.get("gated"):
            print(f"  {r['short']}: INSUFFICIENT-HR-DENSITY ({r['gate_reason']})")
            continue
        dp_min = r["deep_tot_min"]
        print(f"  {r['short']} (Deep total {dp_min:.1f} min):")
        for W, eps in [(60, r['ep60']), (90, r['ep90']), (120, r['ep120'])]:
            tot = sum(e[2] for e in eps) / 60.0
            print(f"    sustain>={W:3d}s : {len(eps):3d} episodes, total {tot:.1f} min in low-SD")
        print(f"    SD up→down round-trips within 60s inside Deep: {r['sub60_round_trips']}")

    print()
    print("--- Q4 detail: dual-trigger replay ---")
    for r in results:
        if r.get("gated"):
            print(f"  {r['short']}: INSUFFICIENT-HR-DENSITY ({r['gate_reason']})")
            continue
        a, b = r["ref_iv"]
        print(f"  {r['short']}: Light-ref HR = {r['ref_hr']:.1f} bpm "
              f"(from Core stretch {(b-a)/60:.1f} min);  HR threshold = {r['hr_thr']:.1f} bpm")
        print(f"    fires total={len(r['fires'])}  in-Deep={len(r['fires_in_deep'])}  out-Deep={len(r['fires_out_deep'])}")
        for d in r["deep_fires_per_stretch"]:
            offs = d["first_fire_offset"]
            offs_s = f"{offs:+.0f}s after onset" if offs is not None else "no fire"
            print(f"    Deep stretch {d['dur_s']/60:5.1f}min: {d['n_fires']} fires, first @ {offs_s}")

    # ===== Plots =====  (gated sessions are excluded from all SD plots)
    if not dense:
        print()
        print("(No dense sessions — all SD-dependent plots skipped.)")
    # Q1 distributions
    if dense:
        fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), sharey=False)
        bins = np.arange(0, 5.0 + 0.05, 0.05)
        for ax, key, title in zip(axes, ["deep_sd", "core_sd"], ["Rolling 60s HR-SD in Apple AsleepDeep", "...in Apple AsleepCore"]):
            for r, color in zip(dense, ("tab:blue", "tab:orange")):
                ax.hist(r[key], bins=bins, alpha=0.55, color=color, label=f"{r['short']} ({r['label']})")
            ax.axvline(T_VAR, color="red", linestyle="--", linewidth=1, label=f"t_var={T_VAR}")
            ax.set_xlabel("rolling-60s HR-SD (bpm)")
            ax.set_ylabel("samples")
            ax.set_title(title)
            ax.legend()
        fig.suptitle(f"Q1: HR-SD distribution in Deep vs Core (n={len(dense)} dense overnights)")
        fig.tight_layout()
        p1 = f"{OUT_DIR}/q1_hr_sd_distribution.png"
        fig.savefig(p1, dpi=120)
        print(f"\nsaved Q1 plot -> {p1}")

    # Q2 overlay
    all_hr = [o for r in dense for o in r["overlays_hr"]]
    all_sd = [o for r in dense for o in r["overlays_sd"]]
    if all_hr and all_sd:
        hr_arr = np.vstack(all_hr)
        sd_arr = np.vstack(all_sd)
        fixed = np.arange(-TRANS_HALF, TRANS_HALF + 1)
        fig2, ax = plt.subplots(1, 1, figsize=(9, 4.5))
        for row in hr_arr:
            ax.plot(fixed, row, color="tab:blue", alpha=0.18, linewidth=0.7)
        for row in sd_arr:
            ax.plot(fixed, row, color="tab:red", alpha=0.18, linewidth=0.7)
        ax.plot(fixed, hr_arr.mean(axis=0), color="tab:blue", linewidth=2.5, label=f"HR (z-norm), mean of n={len(all_hr)} transitions")
        ax.plot(fixed, sd_arr.mean(axis=0), color="tab:red", linewidth=2.5, label=f"rolling-SD (z-norm), mean")
        ax.axvline(0, color="black", linestyle=":", linewidth=1, label="Apple Deep onset")
        ax.set_xlabel("seconds relative to Apple-scored Deep onset")
        ax.set_ylabel("z-normalized")
        ax.set_title("Q2: HR-level and HR-SD trajectory at Deep onset (overlay + mean)")
        ax.legend()
        fig2.tight_layout()
        p2 = f"{OUT_DIR}/q2_deep_onset_overlay.png"
        fig2.savefig(p2, dpi=120)
        print(f"saved Q2 plot -> {p2}")

    # Q3 visualization: SD time series with Deep shading (dense only)
    if dense:
        fig3, axes3 = plt.subplots(len(dense), 1, figsize=(12, 3.0 * len(dense)), sharex=False)
        if len(dense) == 1:
            axes3 = [axes3]
        for ax, r in zip(axes3, dense):
            ax.plot(r["t_grid"] - r["t_grid"][0], r["sd_grid"], color="tab:purple", linewidth=0.7)
            ax.axhline(T_VAR, color="red", linestyle="--", linewidth=1)
            for a, b in r["deep_iv"]:
                ax.axvspan(a - r["t_grid"][0], b - r["t_grid"][0], color="tab:blue", alpha=0.15)
            ax.set_ylim(0, 3.0)
            ax.set_ylabel("rolling-60s HR-SD")
            ax.set_title(f"{r['short']} ({r['label']}) — SD over session; Deep shaded; t_var line at {T_VAR}")
        axes3[-1].set_xlabel("seconds from session start")
        fig3.tight_layout()
        p3 = f"{OUT_DIR}/q3_sd_timeseries_with_deep.png"
        fig3.savefig(p3, dpi=120)
        print(f"saved Q3 plot -> {p3}")

    # Q4 visualization: HR + threshold + Deep shading + fires (dense only)
    if dense:
        fig4, axes4 = plt.subplots(len(dense), 1, figsize=(12, 3.0 * len(dense)), sharex=False)
        if len(dense) == 1:
            axes4 = [axes4]
        for ax, r in zip(axes4, dense):
            t0 = r["t_grid"][0]
            ax.plot(r["t_grid"] - t0, r["bpm_grid"], color="tab:gray", linewidth=0.7)
            ax.axhline(r["hr_thr"], color="red", linestyle="--", linewidth=1, label=f"HR thr = ref-5 = {r['hr_thr']:.1f}")
            ax.axhline(r["ref_hr"], color="green", linestyle=":", linewidth=1, label=f"ref = {r['ref_hr']:.1f}")
            for a, b in r["deep_iv"]:
                ax.axvspan(a - t0, b - t0, color="tab:blue", alpha=0.15)
            for fa, ra, rb in r["fires"]:
                ax.axvline(fa - t0, color="tab:red", linewidth=1)
            ax.set_ylabel("HR (bpm)")
            ax.set_title(f"{r['short']} ({r['label']}) — HR; Deep shaded; vertical lines = dual-trigger fires")
            ax.legend(loc="upper right")
        axes4[-1].set_xlabel("seconds from session start")
        fig4.tight_layout()
        p4 = f"{OUT_DIR}/q4_trigger_replay.png"
        fig4.savefig(p4, dpi=120)
        print(f"saved Q4 plot -> {p4}")

    # ===== Framed conclusions =====
    print()
    print("=" * 110)
    print("CONCLUSIONS — framed as SHAPE vs PARAMETER, and deprivation-sensitivity")
    print("=" * 110)
    if not dense:
        print("\n(All sessions GATED for insufficient HR density — no SD-dependent conclusions.)\n")
        return
    print(f"""
n = {len(dense)} dense overnight(s), SAME SUBJECT, BOTH SLEEP-DEPRIVED.

SHAPE conclusions (structurally robust — threshold-below-the-floor reasoning holds
regardless of physiological state, since adding HRV to a deprivation-suppressed
baseline can only INCREASE SD, not decrease it):

  Q1 — t_var=0.8 vs HR-SD floor in Deep:
    Pooled in-Deep median rolling-SD = {pp_deep.get('p50', float('nan')):.2f} bpm; Core median = {pp_core.get('p50', float('nan')):.2f}.
    Fraction of in-Deep windows with SD<0.8 = {frac_deep_pool*100:.1f}%.
    Shape claim: { 'Deep SD distribution is well below 0.8 → 0.8 sits ABOVE the floor and most Deep windows DO satisfy t_var; the threshold is not gating Deep out by floor mismatch.' if pp_deep.get('p50',1.0) < T_VAR and frac_deep_pool > 0.5 else '0.8 sits at or below the Deep SD floor → many real Deep windows fail t_var; the threshold is structurally too tight.' }
    Parameter claim ("what t_var should be"): NOT SUPPORTED by this data —
    requires rested-physiology data before setting.

  Q2 — synchrony of HR-level vs HR-SD at Deep onset:
    Mean lag (SD-inflect − HR-inflect) = {mean_lag:+.1f}s; median = {median_lag:+.1f}s;
    SD-leads-HR sign consistency: {n_neg}/{len(lags_pool)}.
    Shape claim: { 'SD compression consistently precedes HR-level decline → "SD first" is the leading edge of Deep transitions; an HR-AND-SD gate that requires both to clear simultaneously will fire late.' if mean_lag < -10 and n_neg/max(len(lags_pool),1) >= 0.6 else ('HR-level decline tends to precede SD compression → an AND-gate fires when SD catches up, which is roughly Deep-onset itself.' if mean_lag > 10 else 'Lag is near zero / inconsistent in sign — no clean "one leads the other" claim on these n={} transitions.'.format(len(lags_pool))) }

  Q3 — sustain window vs sub-minute SD volatility in Deep:
    Sustained low-SD episodes inside Deep: W=60 -> {n60}, W=90 -> {n90}, W=120 -> {n120}.
    Shape claim: { '60s does NOT appear to be over-reset by sub-minute fluctuations: lengthening the sustain window gives substantially fewer (or no more) qualifying episodes.' if n60 >= n90 >= n120 and n60 > 0 else 'Longer sustain windows produce comparable or more episodes — suggests 60s is constantly re-triggering on sub-minute SD volatility, consistent with CAP-rhythm reset hypothesis.' if n90 > n60 else 'Inconclusive on this data.' }

  Q4 — does the dual trigger actually fire in scored Deep?
    Fires in-Deep: {n_fires_in} / {n_fires_total} total; Deep stretches with ≥1 fire: {n_deep_with_fire}/{n_deep_stretches}.
    Shape claim: { f'The dual trigger DOES detect Apple-scored Deep ({n_deep_with_fire}/{n_deep_stretches} stretches fire). Shape is workable; deeper question is parameter timing not structural failure.' if n_deep_with_fire >= max(1, n_deep_stretches//2) else f'The dual trigger fails to detect Apple-scored Deep ({n_deep_with_fire}/{n_deep_stretches} stretches fire) — structural failure: the AND-of-both is incompatible with how Deep manifests in this physiology.' }

PARAMETER claims (NOT supported by n=2 deprived data): any numeric recommendation
for t_var, t_hr_drop, or d_sustain; absolute SD values are deprivation-sensitive
(HRV is suppressed in sleep-deprived sleep, so the SD distributions here are
shifted LOWER than rested baseline). Requires rested-physiology data before setting.

Deprivation-sensitivity of the four findings:
  Q1 distribution shape (Deep ABOVE / BELOW threshold): the *direction* is robust
    in the conservative direction — if 0.8 is ABOVE deprived Deep SD, it is even
    more likely above rested Deep SD (deprivation suppresses HRV). If 0.8 is
    BELOW deprived Deep SD, rested Deep SD is likely higher still, so the
    "threshold below the floor" claim STRENGTHENS in rested data. The exact
    percentile, however, is deprivation-sensitive.
  Q2 lag direction: physiology of autonomic transitions at Deep onset; not
    obviously deprivation-flipped. Treat as suggestive.
  Q3 CAP-rhythm reset count: CAP frequency itself can shift with state;
    deprivation-sensitive numeric, but the existence/absence of sub-minute reset
    is structural.
  Q4 fires/no-fires: a function of both shape and parameters. If the trigger
    NEVER fires in Deep on deprived data (where it should be EASIER to satisfy
    HR-drop and low-SD due to suppressed autonomics), no-fire is a strong shape
    indictment. If it fires reliably, the result is reassuring but doesn't
    generalize cleanly to rested.
""")


if __name__ == "__main__":
    main()
