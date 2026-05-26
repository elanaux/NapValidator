# Onset-variance surfacing pass — numbers only

Run: 2026-05-26. Script: `research/onset_variance_pull.py`. Figure: `research/onset_variance.png`.
Descriptive only — no modeling, no product conclusions.

**Definition (both sources):** "sustained sleep onset" = start of first run of ≥3
consecutive 30 s sleep epochs (≥90 s). Latency = onset − recording start.

## Source 1 — my recovered sessions (HR + Apple stages, no EEG)
- **Naps (product-relevant): 0 measurable.** Nap sessions have HR only, no stage
  files; Apple labels nap-length sleep `AsleepUnspecified` (0 min Core/Deep/REM),
  so "first Core/Deep/REM run" is structurally absent.
- **Overnights:** anchor = session `startTimestamp`. Only 4 of 7 have an anchor
  (3 lack a session JSON / HR began mid-sleep → uncapturable). Of those 4, only 2
  carry Core/Deep/REM staging; 2 are Unspecified-only.
  - strict {Core/Deep/REM}, n=2: 5.5, 10.0 min (median 7.8)
  - any-asleep (+Unspecified), n=4: 5.5, 6.0, 6.5, 10.0 min (median 6.2, SD 2.0, IQR 1.5)
- n is single-digit → point values, not a distribution. Cannot read "tightness."

## Source 2 — BidSleep (EEG expert labels; usable nights from locked alignment_table)
**CAVEAT: BidSleep is OVERNIGHT, not naps. Onset-to-Deep here is a proxy for the
nap figure, not identical (nap sleep pressure/architecture differ).**
Scope: 166 usable nights / 45 subjects. Onset metrics are label/epoch-space → independent of HR↔label offset.

| distribution | n | min | Q1 | median | Q3 | max | mean | SD | IQR |
|---|---|---|---|---|---|---|---|---|---|
| [4] onset latency (min) | 166 | 0.0 | 9.6 | 15.0 | 25.4 | 119.0 | 21.2 | 19.6 | 15.8 |
| [5] onset→Deep (min) | 166 | 0.0 | 8.0 | 12.0 | 16.4 | 52.0 | 13.2 | 8.5 | 8.4 |

(All 166 nights reach N3; 0 censored.)

### [6] Within-subject onset→Deep spread (42 subjects with ≥2 N3 nights)
| spread metric (min) | n | min | Q1 | median | Q3 | max | mean | SD |
|---|---|---|---|---|---|---|---|---|
| within-subj SD | 42 | 0.0 | 3.0 | 5.4 | 8.2 | 16.0 | 6.1 | 4.1 |
| within-subj half-range | 42 | 0.0 | 3.2 | 5.9 | 8.1 | 22.5 | 6.8 | 5.0 |
| within-subj max dev from own mean | 42 | 0.0 | 3.3 | 7.1 | 9.6 | 34.9 | 8.1 | 6.6 |

**Pre-registered ±10 min read (number only):**
- worst night deviates >10 min from own mean: **10/42 (24%)**
- half-range >10 min: 7/42 (17%)
- within-subject SD >10 min: 8/42 (19%)
- median within-subject SD = 5.4 min; median half-range = 5.9 min
- **FLAG: NO** — most subjects stay within ±10 min of their own mean.
