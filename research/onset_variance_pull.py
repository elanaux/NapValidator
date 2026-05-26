"""Onset-variance surfacing pass (data-light).

Measures, descriptively only (no modeling, no product conclusions):
  S1. My recovered sessions  -> onset LATENCY (HR + Apple stages, no EEG).
  S2. BidSleep aligned corpus -> onset LATENCY, onset-to-DEEP, and the
      within-subject onset-to-Deep spread.

Definitions
-----------
"Sustained sleep onset" = start of the FIRST run of >= 3 consecutive 30 s
sleep epochs (>= 90 s of continuous sleep). The 3-epoch rule rejects single
transient sleep epochs.

S1 (Apple): sleep_strict = stage in {Core, Deep, REM} (the user's set).
            sleep_any    = strict + AsleepUnspecified (Apple's nap label).
            Anchor (t=0) = session startTimestamp (the lie-down / Start press).
            Latency = onset_time - anchor.
S2 (EEG, AASM 0=Wake 1=N1 2=N2 3=N3 4=REM): sleep = non-Wake.
            Epoch 0 = recStart. Latency = onset_idx * 0.5 min.
            Onset-to-Deep = (first N3 epoch at/after onset - onset_idx) * 0.5 min.

Scope: BidSleep uses ONLY usable==True nights from the locked
alignment_table.csv (yesterday's alignment; NOT re-derived). Onset metrics
are pure label-space (epoch index) quantities, so they are independent of the
HR<->label time offset; the alignment table is used only for its usability gate.
"""
from __future__ import annotations
import csv, glob, json, os
from collections import defaultdict
import numpy as np
from scipy.io import loadmat
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = "/Users/elanaux/Desktop/nap-app"
BID = f"{ROOT}/NapValidator/research/bidsleep"
EPOCH_S = 30.0
RUN = 3  # epochs for "sustained"


def stats(x):
    x = np.asarray([v for v in x if v == v], float)
    if x.size == 0:
        return None
    q1, med, q3 = np.percentile(x, [25, 50, 75])
    return dict(n=int(x.size), min=float(x.min()), q1=float(q1), median=float(med),
                q3=float(q3), max=float(x.max()), mean=float(x.mean()),
                sd=float(x.std(ddof=1)) if x.size > 1 else float("nan"),
                iqr=float(q3 - q1))


def pstat(label, s, unit="min"):
    if s is None:
        print(f"  {label}: (no data)"); return
    print(f"  {label}: n={s['n']}")
    print(f"     min={s['min']:.1f}  Q1={s['q1']:.1f}  median={s['median']:.1f}  "
          f"Q3={s['q3']:.1f}  max={s['max']:.1f}  {unit}")
    print(f"     mean={s['mean']:.1f}  SD={s['sd']:.1f}  IQR={s['iqr']:.1f}  {unit}")


def first_sustained(is_sleep):
    """Index of first epoch starting a run of >=RUN consecutive sleep epochs."""
    c = 0
    for i, s in enumerate(is_sleep):
        c = c + 1 if s else 0
        if c >= RUN:
            return i - RUN + 1
    return None


# ----------------------------------------------------------------------------
# SOURCE 1 : my recovered sessions
# ----------------------------------------------------------------------------
def load_anchors():
    a = {}
    for p in glob.glob(f"{ROOT}/sessions/**/*.json", recursive=True):
        try:
            d = json.load(open(p))
        except Exception:
            continue
        st = d.get("startTimestamp")
        if st:
            a[os.path.basename(p)[:-5]] = float(st)  # stem -> start
    return a


SLEEP_STRICT = {"AsleepCore", "AsleepDeep", "AsleepREM"}
SLEEP_ANY = SLEEP_STRICT | {"AsleepUnspecified"}


def seg_label_grid(segs, anchor, sleepset):
    """30 s grid from anchor..last segment end; True where covering seg is sleep."""
    t_end = max(s["end_t"] for s in segs)
    n = int(np.ceil((t_end - anchor) / EPOCH_S))
    if n <= 0:
        return np.array([], bool)
    mids = anchor + (np.arange(n) + 0.5) * EPOCH_S
    out = np.zeros(n, bool)
    for s in segs:
        if s["value"] in sleepset:
            out |= (mids >= s["start_t"]) & (mids < s["end_t"])
    return out


def source1():
    print("=" * 78)
    print("SOURCE 1 - my recovered sessions (HR + Apple stages, NO EEG)")
    print("  Onset LATENCY only. Anchor t=0 = session startTimestamp.")
    print("  Sustained = first run of >=3 consecutive 30s sleep epochs.")
    print("=" * 78)
    anchors = load_anchors()

    # naps: HR only, no stages
    nap_hr = sorted(glob.glob(f"{ROOT}/sessions_recovered/nap/*.hr.json"))
    nap_st = glob.glob(f"{ROOT}/sessions_recovered/nap/*.stages.json")
    print(f"\nNAPS (product-relevant): {len(nap_hr)} HR files, "
          f"{len(nap_st)} stage files.")
    print("  -> Apple assigns NO Core/Deep/REM staging to nap-length sleep")
    print("     (the apple_sleep export labels a 74-min daytime sleep entirely")
    print("     'AsleepUnspecified', 0 min Core/Deep/REM). Nap onset latency is")
    print("     therefore NOT measurable from Apple stage labels.  n_nap_latency = 0")

    lat_strict, lat_any = [], []
    rows = []
    for sf in sorted(glob.glob(f"{ROOT}/sessions_recovered/overnight/*.stages.json")):
        stem = os.path.basename(sf)[:-len(".stages.json")]
        segs = json.load(open(sf))
        anchor = anchors.get(stem)
        rec = {"name": stem, "anchor": anchor}
        if anchor is None:
            rec["note"] = "no session startTimestamp anchor -> latency uncapturable"
            rows.append(rec); continue
        gS = seg_label_grid(segs, anchor, SLEEP_STRICT)
        gA = seg_label_grid(segs, anchor, SLEEP_ANY)
        iS, iA = first_sustained(gS), first_sustained(gA)
        rec["lat_strict"] = iS * 0.5 if iS is not None else None
        rec["lat_any"] = iA * 0.5 if iA is not None else None
        rec["staged"] = "Core/Deep/REM" if any(s["value"] in SLEEP_STRICT for s in segs) else "Unspecified-only"
        if rec["lat_strict"] is not None:
            lat_strict.append(rec["lat_strict"])
        if rec["lat_any"] is not None:
            lat_any.append(rec["lat_any"])
        rows.append(rec)

    print("\nOVERNIGHTS (have Apple stages):")
    for r in rows:
        if r["anchor"] is None:
            print(f"  {r['name']:40s} -> SKIP ({r['note']})")
        else:
            ls = f"{r['lat_strict']:.1f}" if r['lat_strict'] is not None else "n/a"
            la = f"{r['lat_any']:.1f}" if r['lat_any'] is not None else "n/a"
            print(f"  {r['name']:40s} [{r['staged']:>16s}]  "
                  f"latency strict={ls:>5s}  any-asleep={la:>5s} min")

    print("\nOvernight latency distribution (strict Core/Deep/REM):")
    pstat("strict", stats(lat_strict))
    print("Overnight latency distribution (any-asleep, incl. Unspecified):")
    pstat("any", stats(lat_any))
    print("  NOTE: n is tiny (single-digit). These are point values, not a")
    print("        distribution you can read 'tightness' from.")
    return dict(lat_strict=lat_strict, lat_any=lat_any)


# ----------------------------------------------------------------------------
# SOURCE 2 : BidSleep
# ----------------------------------------------------------------------------
def usable_nights():
    rows = list(csv.DictReader(open(f"{BID}/alignment_table.csv")))
    return [(r["subject"], r["night"]) for r in rows if r["usable"] == "True"]


def night_metrics(subj, night):
    m = loadmat(f"{BID}/{subj}/{night}/labels.mat")
    lab = np.asarray(m["expert_label"]).flatten().astype(int)
    is_sleep = lab != 0                      # non-Wake
    onset = first_sustained(is_sleep)
    if onset is None:
        return None
    lat = onset * 0.5
    n3 = np.where(lab[onset:] == 3)[0]       # first N3 at/after onset
    o2d = float(n3[0] * 0.5) if n3.size else None
    return lat, o2d


def source2():
    print("\n" + "=" * 78)
    print("SOURCE 2 - BidSleep aligned corpus (EEG expert labels)")
    print("  CAVEAT: BidSleep is OVERNIGHT, not naps. Onset-to-Deep overnight is a")
    print("          PROXY for the nap figure, not identical (nap sleep pressure /")
    print("          architecture differ). Do not over-trust as a nap number.")
    print("  Scope: usable==True nights from locked alignment_table.csv.")
    print("=" * 78)
    nights = usable_nights()
    subs = sorted(set(s for s, _ in nights))
    print(f"\nUsable nights: {len(nights)}  across {len(subs)} subjects.")

    lat, o2d = [], []
    by_subj = defaultdict(list)
    n_no_n3 = 0
    for s, n in nights:
        r = night_metrics(s, n)
        if r is None:
            continue
        L, D = r
        lat.append(L)
        if D is None:
            n_no_n3 += 1
        else:
            o2d.append(D)
            by_subj[s].append(D)

    print("\n[4] Onset latency across nights (recStart -> sustained sleep):")
    pstat("latency", stats(lat))

    print(f"\n[5] Onset-to-Deep across nights (sustained sleep -> first N3):")
    print(f"    nights with N3 reached: {len(o2d)};  no N3 all night: {n_no_n3}")
    pstat("onset-to-Deep", stats(o2d))

    # [6] within-subject spread
    print("\n[6] WITHIN-SUBJECT onset-to-Deep spread (subjects with >=2 nights w/ N3):")
    ws_sd, ws_halfrange, ws_maxdev, kept = [], [], [], []
    for s in sorted(by_subj):
        v = np.asarray(by_subj[s], float)
        if v.size < 2:
            continue
        mean = v.mean()
        sd = v.std(ddof=1)
        halfr = (v.max() - v.min()) / 2
        maxdev = np.abs(v - mean).max()
        ws_sd.append(sd); ws_halfrange.append(halfr); ws_maxdev.append(maxdev)
        kept.append((s, v.size, mean, sd, halfr, maxdev))
    print(f"    subjects qualifying: {len(kept)}")
    print(f"    {'subject':10s} {'n':>2s} {'mean':>6s} {'SD':>6s} {'half-rng':>8s} {'maxdev':>7s}")
    for s, k, mean, sd, hr, md in kept:
        print(f"    {s:10s} {k:2d} {mean:6.1f} {sd:6.1f} {hr:8.1f} {md:7.1f}")

    print("\n    Distribution of within-subject SD (min) across subjects:")
    pstat("within-subj SD", stats(ws_sd))
    print("    Distribution of within-subject half-range (min):")
    pstat("within-subj half-range", stats(ws_halfrange))
    print("    Distribution of within-subject max deviation from own mean (min):")
    pstat("within-subj max-dev", stats(ws_maxdev))

    # ±10 min flag (pre-registered read)
    md = np.asarray(ws_maxdev)
    hr = np.asarray(ws_halfrange)
    sd = np.asarray(ws_sd)
    frac_maxdev = float((md > 10).mean())
    frac_halfr = float((hr > 10).mean())
    frac_sd = float((sd > 10).mean())
    print("\n    >>> PRE-REGISTERED READ: does typical within-subject onset-to-Deep")
    print("        spread exceed +/-10 min around the subject's own mean?")
    print(f"        - subjects whose worst night deviates >10 min from own mean: "
          f"{int((md>10).sum())}/{len(md)} ({frac_maxdev*100:.0f}%)")
    print(f"        - subjects whose half-range exceeds 10 min: "
          f"{int((hr>10).sum())}/{len(hr)} ({frac_halfr*100:.0f}%)")
    print(f"        - subjects whose within-subject SD exceeds 10 min: "
          f"{int((sd>10).sum())}/{len(sd)} ({frac_sd*100:.0f}%)")
    print(f"        - median within-subject SD = {np.median(sd):.1f} min; "
          f"median half-range = {np.median(hr):.1f} min")
    flag = "YES - most subjects swing > +/-10 min (moving target)" if frac_maxdev > 0.5 \
        else "NO - most subjects stay within +/-10 min of their own mean"
    print(f"        FLAG: {flag}")
    return dict(lat=lat, o2d=o2d, ws_sd=ws_sd, ws_halfrange=ws_halfrange,
                ws_maxdev=ws_maxdev)


def figures(s1, s2):
    fig, ax = plt.subplots(2, 2, figsize=(11, 8))
    a = ax[0, 0]
    a.hist(s2["lat"], bins=20, color="#4477aa", edgecolor="w")
    a.axvline(np.median(s2["lat"]), color="k", ls="--", lw=1,
              label=f"median {np.median(s2['lat']):.1f}m")
    a.set_title(f"BidSleep onset latency (n={len(s2['lat'])} nights)")
    a.set_xlabel("min"); a.legend()

    a = ax[0, 1]
    a.hist(s2["o2d"], bins=20, color="#ee6677", edgecolor="w")
    a.axvline(np.median(s2["o2d"]), color="k", ls="--", lw=1,
              label=f"median {np.median(s2['o2d']):.1f}m")
    a.set_title(f"BidSleep onset->Deep (n={len(s2['o2d'])} nights)\n[OVERNIGHT proxy, not naps]")
    a.set_xlabel("min"); a.legend()

    a = ax[1, 0]
    a.hist(s2["ws_sd"], bins=15, color="#228833", edgecolor="w")
    a.axvline(10, color="r", ls="-", lw=1.5, label="+/-10 min ref")
    a.axvline(np.median(s2["ws_sd"]), color="k", ls="--", lw=1,
              label=f"median {np.median(s2['ws_sd']):.1f}m")
    a.set_title(f"Within-subject onset->Deep SD (n={len(s2['ws_sd'])} subj)")
    a.set_xlabel("min"); a.legend()

    a = ax[1, 1]
    a.hist(s2["ws_maxdev"], bins=15, color="#aa3377", edgecolor="w")
    a.axvline(10, color="r", ls="-", lw=1.5, label="+/-10 min flag")
    a.set_title("Within-subject max night deviation from own mean")
    a.set_xlabel("min"); a.legend()

    # annotate S1 tiny-n on the figure for context
    txt = (f"S1 my-sessions overnight latency (tiny n): "
           f"strict={[round(x,1) for x in s1['lat_strict']]}  "
           f"any-asleep={[round(x,1) for x in s1['lat_any']]} min;  naps: 0 measurable")
    fig.text(0.5, 0.005, txt, ha="center", fontsize=8, color="#444")
    fig.suptitle("Onset-variance surfacing pass", fontweight="bold")
    fig.tight_layout(rect=[0, 0.03, 1, 0.97])
    out = f"{ROOT}/research/onset_variance.png"
    fig.savefig(out, dpi=120)
    print(f"\nFigure saved: {out}")


if __name__ == "__main__":
    s1 = source1()
    s2 = source2()
    figures(s1, s2)
