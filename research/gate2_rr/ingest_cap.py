"""Gate 2 Step 2 — CAP ingestion: ECG -> R-peaks -> clean NN -> (a) 5 s HR, (b) RR series.

Rules are fixed in gate-2-preregistration.md (Amendments 4-5). Per usable record:
  1. STREAM the EDF over HTTP and keep only the ECG channel (full EDFs total
     ~42 GB; disk can't hold them, so nothing but the ECG is ever written).
     ECG1/ECG2 stored separately -> ECG1 - ECG2.
  2. neurokit2.ecg_clean + ecg_peaks (method "neurokit"); R-peak times refined by
     parabolic interpolation on the cleaned ECG.
  3. RR QC: drop RR outside 300-2000 ms; drop RR deviating > 20 % from the median
     of the PRECEDING 11 accepted-range RR (causal, Amendment 5).
  4. % removed reported over the scored window (the exclusion basis) and over
     the whole recording. Exclude record if scored-window removal > 20 %.
  5. 5 s HR: mean 60000/NN of clean beats in (end-5, end], integer-rounded,
     timestamped at bin end; empty bins omitted.
  6. Labels: 30 s epochs placed by clock time from EDF start; S3|S4 -> 3 (N3);
     W 0, S1 1, S2 2, REM 4, MT/unscored/gaps 5 (UNKNOWN); epochs not wholly
     inside the recording are trimmed.
Outputs (gitignored): cap_derived/<rec>.npz. Committed: cap_ingest_qc.csv.
"""
from __future__ import annotations

import csv
import hashlib
import os
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(ROOT, "cap_raw")
OUT = os.path.join(ROOT, "cap_derived")
BASE = "https://physionet.org/files/capslpdb/1.0.0/"
# EDFs are streamed from PhysioNet's official AWS open-data mirror (physionet.org
# serves ~0.17 MB/s here vs ~29 MB/s on the mirror); every stream is SHA256-checked
# against PhysioNet's own SHA256SUMS.txt, so the source can't silently differ.
EDF_BASE = "https://physionet-open.s3.amazonaws.com/capslpdb/1.0.0/"
EXCLUDED = {"n16": "no ECG", "rbd11": "duplicate of rbd10", "nfle27": "clock contradiction"}
TRUE_NREC = {}  # filled from file size when header says -1
EPOCH_S = 30.0
STAGE = {"SLEEP-S0": 0, "SLEEP-S1": 1, "SLEEP-S2": 2, "SLEEP-S3": 3, "SLEEP-S4": 3,
         "SLEEP-REM": 4, "SLEEP-MT": 5, "SLEEP-UNSCORED": 5}
UNKNOWN = 5
RR_MIN, RR_MAX = 300.0, 2000.0
MED_N, MED_TOL = 11, 0.20
EXCLUDE_FRAC = 0.20
BIN_S = 5.0


# ---------- EDF streaming ----------

def parse_header(h: str):
    ns = int(h[252:256])
    o = 256
    def field(w):
        nonlocal o
        v = [h[o + i * w:o + (i + 1) * w].strip() for i in range(ns)]
        o += w * ns
        return v
    labels = field(16); field(80); field(8)
    pmin = [float(x) for x in field(8)]; pmax = [float(x) for x in field(8)]
    dmin = [float(x) for x in field(8)]; dmax = [float(x) for x in field(8)]
    field(80); nsamp = [int(x) for x in field(8)]
    return dict(ns=ns, hdr_len=256 + 256 * ns, labels=labels, nsamp=nsamp,
                pmin=pmin, pmax=pmax, dmin=dmin, dmax=dmax,
                start=datetime.strptime(h[168:176] + " " + h[176:184], "%d.%m.%y %H.%M.%S"),
                n_rec=int(h[236:244]), rec_dur=float(h[244:252]))


def ecg_channels(labels):
    idx = [i for i, l in enumerate(labels) if re.search(r"(ECG|EKG)", l, re.I)]
    if len(idx) == 2 and all(re.fullmatch(r"ECG[12]", labels[i], re.I) for i in idx):
        return idx  # separate leads -> difference
    return idx[:1]


def stream_ecg(rec):
    """Download rec.edf as a stream; return (ecg_physical float32, fs, hdr)."""
    path = os.path.join(RAW, f"{rec}_ecg.npz")
    hdr = parse_header(open(os.path.join(RAW, f"{rec}.edf.fullhdr"), "rb").read().decode("latin-1"))
    if os.path.exists(path):
        z = np.load(path)
        return z["ecg"], float(z["fs"]), hdr
    idx = ecg_channels(hdr["labels"])
    nsamp = np.array(hdr["nsamp"])
    offs = np.concatenate([[0], np.cumsum(nsamp)])
    rec_len = int(offs[-1])
    fs = nsamp[idx[0]] / hdr["rec_dur"]
    sums = dict(l.split()[::-1] for l in open(os.path.join(RAW, "SHA256SUMS.txt")) if l.strip())
    sha = hashlib.sha256()
    resp = urllib.request.urlopen(EDF_BASE + rec + ".edf", timeout=300)
    head = resp.read(hdr["hdr_len"])
    sha.update(head)
    chunks, buf = [], b""
    CH = 256  # data records per read
    while True:
        data = resp.read(rec_len * 2 * CH)
        if not data:
            break
        sha.update(data)
        buf += data
        n_full = len(buf) // (rec_len * 2)
        if n_full == 0:
            continue
        arr = np.frombuffer(buf[:n_full * rec_len * 2], dtype="<i2").reshape(n_full, rec_len)
        buf = buf[n_full * rec_len * 2:]
        sig = []
        for i in idx:
            d = arr[:, offs[i]:offs[i + 1]].astype(np.float32).ravel()
            g = (hdr["pmax"][i] - hdr["pmin"][i]) / (hdr["dmax"][i] - hdr["dmin"][i])
            sig.append((d - hdr["dmin"][i]) * g + hdr["pmin"][i])
        chunks.append(sig[0] - sig[1] if len(sig) == 2 else sig[0])
    if sha.hexdigest() != sums[rec + ".edf"]:
        raise RuntimeError(f"{rec}: SHA256 mismatch vs PhysioNet SHA256SUMS")
    ecg = np.concatenate(chunks).astype(np.float32)
    np.savez(path, ecg=ecg, fs=fs)
    return ecg, float(fs), hdr


# ---------- hypnogram ----------

def load_labels(rec, start, dur_s):
    raw = open(os.path.join(RAW, f"{rec}.txt"), "rb").read().decode("latin-1").splitlines()
    hi = next(i for i, l in enumerate(raw) if l.startswith("Sleep Stage"))
    cols = [c.strip() for c in raw[hi].split("\t")]
    ci = {c: i for i, c in enumerate(cols)}
    tcol = next(c for c in cols if c.startswith("Time"))
    evs = []
    for l in raw[hi + 1:]:
        p = l.split("\t")
        if len(p) < len(cols) - 1 or not p[ci["Event"]].strip().startswith("SLEEP-"):
            continue
        evs.append((p[ci[tcol]].strip(), STAGE.get(p[ci["Event"]].strip(), UNKNOWN)))
    # clock -> seconds from EDF start (roll past midnight)
    secs, day, prev = [], start.date(), None
    for s, _ in evs:
        h, m, sec = [int(x) for x in re.split(r"[:.]", s)[:3]]
        t = datetime.combine(day, datetime.min.time()) + timedelta(hours=h, minutes=m, seconds=sec)
        if (prev is None and t < start - timedelta(hours=1)) or (prev is not None and t < prev - timedelta(hours=1)):
            day += timedelta(days=1); t += timedelta(days=1)
        secs.append((t - start).total_seconds()); prev = t
    secs = np.array(secs)
    rs = secs[0]
    k = np.round((secs - rs) / EPOCH_S).astype(int)
    labels = np.full(k.max() + 1, UNKNOWN, dtype=int)   # gaps -> UNKNOWN
    labels[k] = [st for _, st in evs]
    # trim epochs not wholly inside the recording
    ep_start = rs + np.arange(labels.size) * EPOCH_S
    inside = (ep_start >= 0) & (ep_start + EPOCH_S <= dur_s)
    first, last = np.flatnonzero(inside)[[0, -1]]
    n_trim = labels.size - (last - first + 1)
    return labels[first:last + 1], rs + first * EPOCH_S, n_trim


# ---------- beats ----------

def r_peaks(ecg, fs):
    import neurokit2 as nk
    clean = nk.ecg_clean(ecg, sampling_rate=fs, method="neurokit")
    _, info = nk.ecg_peaks(clean, sampling_rate=fs, method="neurokit")
    pk = np.asarray(info["ECG_R_Peaks"], dtype=int)
    pk = pk[(pk > 0) & (pk < clean.size - 1)]
    y0, y1, y2 = clean[pk - 1], clean[pk], clean[pk + 1]
    den = y0 - 2 * y1 + y2
    with np.errstate(divide="ignore", invalid="ignore"):
        delta = np.where(np.abs(den) > 1e-12, 0.5 * (y0 - y2) / den, 0.0)
    delta = np.clip(delta, -0.5, 0.5)
    return (pk + delta) / fs   # seconds from EDF start


def qc_rr(beat_t):
    """RR[i] = beat_t[i+1]-beat_t[i], timestamped at beat_t[i+1]. Returns (t, rr_ms, keep)."""
    rr = np.diff(beat_t) * 1000.0
    t = beat_t[1:]
    in_range = (rr >= RR_MIN) & (rr <= RR_MAX)
    keep = in_range.copy()
    hist = []  # preceding in-range RR (causal)
    for i in range(rr.size):
        if not in_range[i]:
            continue
        if len(hist) >= MED_N:
            med = np.median(hist[-MED_N:])
            if abs(rr[i] - med) > MED_TOL * med:
                keep[i] = False
        hist.append(rr[i])
    return t, rr, keep


def hr_5s(t, rr, keep, dur_s):
    edges_end = np.arange(BIN_S, dur_s + 1e-9, BIN_S)
    tk, hk = t[keep], 60000.0 / rr[keep]
    b = np.ceil(tk / BIN_S).astype(int) - 1      # bin index for (end-5, end]
    ok = (b >= 0) & (b < edges_end.size)
    s = np.bincount(b[ok], weights=hk[ok], minlength=edges_end.size)
    c = np.bincount(b[ok], minlength=edges_end.size)
    m = c > 0
    return edges_end[m], np.round(s[m] / c[m])


# ---------- main ----------

def process(rec):
    ecg, fs, hdr = stream_ecg(rec)
    dur_s = ecg.size / fs
    labels, rs, n_trim = load_labels(rec, hdr["start"], dur_s)
    beats = r_peaks(ecg, fs)
    t, rr, keep = qc_rr(beats)
    sc = (t >= rs) & (t < rs + labels.size * EPOCH_S)
    rm_scored = 1 - keep[sc].mean() if sc.any() else np.nan
    rm_all = 1 - keep.mean()
    hr_t, hr_bpm = hr_5s(t, rr, keep, dur_s)
    np.savez(os.path.join(OUT, f"{rec}.npz"), rr_t=t, rr_ms=rr, rr_keep=keep,
             hr_t=hr_t, hr_bpm=hr_bpm, labels=labels, rs=rs, fs=fs)
    n3 = labels == 3
    return dict(record=rec, cohort=re.sub(r"\d+$", "", rec), fs=fs, hours=round(dur_s / 3600, 2),
                n_beats=int(beats.size), pct_removed_scored=round(100 * rm_scored, 2),
                pct_removed_all=round(100 * rm_all, 2),
                excluded=bool(rm_scored > EXCLUDE_FRAC), epochs=int(labels.size),
                epochs_trimmed=int(n_trim), n3_onsets=int((n3[1:] & ~n3[:-1]).sum()),
                hr_bins=int(hr_t.size), median_hr=float(np.median(hr_bpm)),
                median_rr_ms=float(np.median(rr[keep])))


def main():
    os.makedirs(OUT, exist_ok=True)
    recs = [r["record"] for r in csv.DictReader(open(os.path.join(ROOT, "cap_fit_table.csv")))
            if r["record"] not in EXCLUDED]
    if len(sys.argv) > 1:
        recs = [r for r in recs if r in sys.argv[1:]]
    # stream ECGs in parallel (network-bound), then process
    with ThreadPoolExecutor(6) as ex:
        for rec, _ in zip(recs, ex.map(lambda r: stream_ecg(r)[1], recs)):
            print(f"  ecg cached: {rec}", flush=True)
    rows = []
    for rec in recs:
        r = process(rec)
        rows.append(r)
        print(f"{rec:8s} fs={r['fs']:>4g} beats={r['n_beats']:>6} removed scored={r['pct_removed_scored']:5.2f}% "
              f"all={r['pct_removed_all']:5.2f}% excl={r['excluded']} N3on={r['n3_onsets']} "
              f"medHR={r['median_hr']:.0f}", flush=True)
    if len(sys.argv) == 1:
        with open(os.path.join(ROOT, "cap_ingest_qc.csv"), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader(); w.writerows(rows)
        use = [r for r in rows if not r["excluded"]]
        print(f"\nUSABLE after beat-removal rule: {len(use)} / {len(rows)} "
              f"(>=200 Hz: {sum(r['fs'] >= 200 for r in use)}), N3 onsets {sum(r['n3_onsets'] for r in use)}")


if __name__ == "__main__":
    main()
