"""Gate 2 Step 1 — fit-verify PhysioNet CAP Sleep Database (capslpdb 1.0.0).

Metadata only: fetches each record's EDF *header* (HTTP byte range, no signal
data) and its RemLogic hypnogram .txt. Verifies, per record:
  - ECG channel present? label, sampling rate, physical unit
  - hypnogram epoch length(s), contiguity, stage counts, R&K S3/S4 presence
  - N3 (S3 ∪ S4) onsets — first N3 epoch after a non-N3 epoch (harness rule)
  - clock alignment: first scored epoch vs EDF start, scored span inside EDF
Writes cap_fit_table.csv next to this script; caches raw files in cap_raw/
(gitignored — do not commit PhysioNet data).
"""
from __future__ import annotations

import csv
import os
import re
import urllib.request
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(ROOT, "cap_raw")
BASE = "https://physionet.org/files/capslpdb/1.0.0/"
ECG_RE = re.compile(r"(ECG|EKG)", re.I)
N3_EVENTS = {"SLEEP-S3", "SLEEP-S4"}


def fetch(name, byte_range=None):
    path = os.path.join(CACHE, name + (".hdr" if byte_range else ""))
    if os.path.exists(path):
        return open(path, "rb").read()
    req = urllib.request.Request(BASE + name)
    if byte_range:
        req.add_header("Range", f"bytes={byte_range[0]}-{byte_range[1]}")
    data = urllib.request.urlopen(req, timeout=60).read()
    with open(path, "wb") as f:
        f.write(data)
    return data


def edf_header(rec):
    head = fetch(rec, (0, 255))
    ns = int(head[252:256])
    hdr_len = 256 + 256 * ns
    # full header (cached under a distinct name)
    path = os.path.join(CACHE, rec + ".fullhdr")
    if os.path.exists(path):
        h = open(path, "rb").read()
    else:
        req = urllib.request.Request(BASE + rec)
        req.add_header("Range", f"bytes=0-{hdr_len - 1}")
        h = urllib.request.urlopen(req, timeout=60).read()
        open(path, "wb").write(h)
    txt = h.decode("latin-1")
    start = datetime.strptime(txt[168:176] + " " + txt[176:184], "%d.%m.%y %H.%M.%S")
    n_rec = int(txt[236:244])
    rec_dur = float(txt[244:252])
    off = 256

    def field(width):
        nonlocal off
        vals = [txt[off + i * width: off + (i + 1) * width].strip() for i in range(ns)]
        off += width * ns
        return vals

    labels = field(16); field(80); dims = field(8); field(8); field(8); field(8); field(8)
    field(80); nsamp = [int(x) for x in field(8)]
    fs = [n / rec_dur for n in nsamp]
    return dict(start=start, dur_s=n_rec * rec_dur, labels=labels, dims=dims, fs=fs)


def hypnogram(rec):
    raw = fetch(rec.replace(".edf", ".txt")).decode("latin-1").splitlines()
    hi = next(i for i, l in enumerate(raw) if l.startswith("Sleep Stage"))
    cols = [c.strip() for c in raw[hi].split("\t")]
    ci = {c: i for i, c in enumerate(cols)}
    tcol = next(c for c in cols if c.startswith("Time"))
    dcol = next(c for c in cols if c.startswith("Duration"))
    epochs = []
    for l in raw[hi + 1:]:
        p = l.split("\t")
        if len(p) < len(cols) - 1:
            continue
        ev = p[ci["Event"]].strip()
        if not ev.startswith("SLEEP-"):
            continue
        epochs.append((p[ci[tcol]].strip(), ev, float(p[ci[dcol]])))
    return epochs


def clock_to_abs(times, anchor):
    """hh:mm:ss (or hh.mm.ss) strings -> datetimes, rolling past midnight, anchored at EDF start date."""
    out, day, prev = [], anchor.date(), None
    for s in times:
        h, m, sec = [int(x) for x in re.split(r"[:.]", s)[:3]]
        t = datetime.combine(day, datetime.min.time()) + timedelta(hours=h, minutes=m, seconds=sec)
        if prev is not None and t < prev - timedelta(hours=1):
            day += timedelta(days=1)
            t += timedelta(days=1)
        if prev is None and t < anchor - timedelta(hours=1):  # scoring starts after midnight
            day += timedelta(days=1)
            t += timedelta(days=1)
        out.append(t)
        prev = t
    return out


def main():
    os.makedirs(CACHE, exist_ok=True)
    recs = fetch("RECORDS").decode().split()
    rows = []
    for rec in recs:
        name = rec.replace(".edf", "")
        r = dict(record=name, cohort=re.sub(r"\d+$", "", name))
        try:
            h = edf_header(rec)
        except Exception as e:  # noqa
            r["error"] = f"edf: {e}"
            rows.append(r)
            continue
        ecg = [(l, f, d) for l, f, d in zip(h["labels"], h["fs"], h["dims"]) if ECG_RE.search(l)]
        r.update(n_signals=len(h["labels"]), edf_hours=round(h["dur_s"] / 3600, 2),
                 ecg_labels="|".join(e[0] for e in ecg), ecg_fs="|".join(f"{e[1]:g}" for e in ecg),
                 ecg_unit="|".join(e[2] for e in ecg), has_ecg=bool(ecg))
        try:
            ep = hypnogram(rec)
        except Exception as e:  # noqa
            r["error"] = f"txt: {e}"
            rows.append(r)
            continue
        durs = sorted({d for _, _, d in ep})
        ts = clock_to_abs([t for t, _, _ in ep], h["start"])
        gaps = [(b - a).total_seconds() - d for a, b, (_, _, d) in zip(ts, ts[1:], ep)]
        evs = [e for _, e, _ in ep]
        is_n3 = [e in N3_EVENTS for e in evs]
        onsets = sum(1 for i in range(1, len(is_n3)) if is_n3[i] and not is_n3[i - 1])
        first_off = (ts[0] - h["start"]).total_seconds()
        end_off = (ts[-1] - h["start"]).total_seconds() + ep[-1][2]
        r.update(n_epochs=len(ep), epoch_s="|".join(f"{d:g}" for d in durs),
                 n_gaps=sum(1 for g in gaps if abs(g) > 0.5), max_gap_s=max(gaps) if gaps else 0,
                 scored_hours=round(sum(d for *_, d in ep) / 3600, 2),
                 n_S3=evs.count("SLEEP-S3"), n_S4=evs.count("SLEEP-S4"),
                 n_REM=evs.count("SLEEP-REM"), n_W=evs.count("SLEEP-S0"),
                 n_MT=evs.count("SLEEP-MT"), n_unscored=evs.count("SLEEP-UNSCORED"),
                 n3_onsets=onsets, first_epoch_off_s=first_off, scored_end_off_s=end_off,
                 fits_in_edf=(first_off >= 0 and end_off <= h["dur_s"] + 1))
        rows.append(r)
        print(f"{name:8s} ecg={r['ecg_labels'] or '-':12s} fs={r['ecg_fs'] or '-':6s} "
              f"ep={r['epoch_s']:5s} N3on={onsets:2d} S3/S4={r['n_S3']}/{r['n_S4']} "
              f"off={first_off:7.0f}s fits={r['fits_in_edf']} gaps={r['n_gaps']}")
    keys = sorted({k for r in rows for k in r}, key=lambda k: list(rows[0]).index(k) if k in rows[0] else 99)
    with open(os.path.join(ROOT, "cap_fit_table.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    print(f"\nwrote cap_fit_table.csv ({len(rows)} records)")


if __name__ == "__main__":
    main()
