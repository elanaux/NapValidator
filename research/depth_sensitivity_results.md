# Depth-threshold sensitivity sweep — numbers only

Run: 2026-05-26. Script: `research/depth_sensitivity_pull.py` (reuses `early_tail_pull.build()`;
locked alignment, no new data). Figure: `research/depth_sensitivity.png`.

**REFRAME (locked):** This sweeps the acceptable-depth threshold to show how sensitive the
failure rate is to where the "still-an-acceptable-wake" line is drawn. NO threshold is
treated as correct — the true line (how many minutes into Deep still feels non-groggy to a
user) is an unresolved empirical question that only field wake-ratings can answer. This is
sensitivity analysis, not goalpost-setting.

**CAVEAT:** BidSleep is OVERNIGHT, not naps (real-nap early-tail plausibly worse);
personal_mean is in-sample (deployed rate plausibly higher); acceptable-depth D is a
TOLERANCE under test, NOT a validated comfort threshold.

Frame: 42 subjects, 163 N3 nights. depth = (personal_mean − margin) − night_o2d (min past
N3 onset). FAILURE iff depth > D.

## Failure-rate grid (%) — margin (rows) × D (cols). D=0 = anchor (matches prior run).
| margin \ D | **D=0** (anchor) | D=1 | D=2 | D=3 | D=5 |
|---|---|---|---|---|---|
| 0 | **53.4** | 44.2 | 37.4 | 30.1 | 17.2 |
| 2 | **37.4** | 30.1 | 22.7 | 17.2 | 11.0 |
| 4 | **22.7** | 17.2 | 14.7 | 11.0 | 7.4 |
| 6 | **14.7** | 11.0 | 9.2 | 7.4 | 3.1 |

n failures:
| margin \ D | D=0 | D=1 | D=2 | D=3 | D=5 |
|---|---|---|---|---|---|
| 0 | 87 | 72 | 61 | 49 | 28 |
| 2 | 61 | 49 | 37 | 28 | 18 |
| 4 | 37 | 28 | 24 | 18 | 12 |
| 6 | 24 | 18 | 15 | 12 | 5 |

## Within-band breakdown (#3): of "acceptable" wakes, before-Deep vs in-tolerance-band
before-Deep count (depth≤0) is D-independent; band count (0<depth≤D) grows with D.

| margin | D | accept_n | before-Deep | in-band (0<d≤D) | %band of accept | fail_n |
|---|---|---|---|---|---|---|
| 0 | 1 | 91 | 76 | 15 | 16% | 72 |
| 0 | 2 | 102 | 76 | 26 | 25% | 61 |
| 0 | 3 | 114 | 76 | 38 | 33% | 49 |
| 0 | 5 | 135 | 76 | 59 | 44% | 28 |
| 2 | 3 | 135 | 102 | 33 | 24% | 28 |
| 4 | 1 | 135 | 126 | 9 | 7% | 28 |
| 4 | 3 | 145 | 126 | 19 | 13% | 18 |
| 6 | 3 | 151 | 139 | 12 | 8% | 12 |
| 6 | 5 | 158 | 139 | 19 | 12% | 5 |
(full 4×5 in script output; at D=0 in-band is 0 by definition → all "successes" are genuinely before Deep.)

## Cost (#4) — nap sacrificed is margin-driven, D-INDEPENDENT
| margin | sacrificed nonfail (min) | sacrificed all (min) |
|---|---|---|
| 0 | 5.2 | 2.4 |
| 2 | 5.6 | 3.5 |
| 4 | 6.3 | 4.9 |
| 6 | 7.7 | 6.5 |

## Tail (#5) — representative cell margin=4, D=3
18 residual failures: **12/18 = 67% from the 8 hard-swingers**, 6/18 = 33% from the rest.
Even-spread baseline = 23% (their share of nights).
