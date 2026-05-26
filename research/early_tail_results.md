# Onset-to-Deep early-tail — numbers only

Run: 2026-05-26. Script: `research/early_tail_pull.py` (imports onset-to-Deep series
from `onset_variance_pull.py`; locked alignment, not re-derived). Figure: `research/early_tail.png`.
Descriptive only — no product interpretation.

**Frame:** 42 subjects with ≥2 N3 nights → **163 nights**. `personal_mean` = in-sample
mean onset-to-Deep per subject. Failure (groggy wake) = night_o2d < (personal_mean − margin),
i.e. Deep arrived before the countdown fired.

**CAVEAT:** BidSleep is OVERNIGHT, not naps. Naps self-select for sleep-deprived states
that may pull Deep earlier AND make it more variable → real nap early-tail plausibly WORSE.
**NOTE:** personal_mean is in-sample (includes the scored night); a deployed mean wouldn't,
so real early-rate is plausibly a touch higher.

## [2] Early deviations (positive = earlier than own mean)
- Fraction of all nights that are early: **87/163 = 53%**
- Pooled early-deviation magnitude (min): n=87, min 0.1, Q1 1.6, **median 3.4**, Q3 6.4, max 15.1, mean 4.5, SD 3.7
- Worst early night per subject (churn tail): n=42, min 0.0, Q1 3.2, **median 5.2**, Q3 8.1, max 15.1, mean 6.0, SD 3.9

## [3] Firing sweep — fire at (personal_mean − margin)
| margin (min) | groggy-wake fail % | n_fail | depth into Deep: median [Q1,Q3] max (min past N3) | nap sacrificed nonfail / all (min) |
|---|---|---|---|---|
| 0 | 53.4% | 87 | 3.4 [1.6, 6.4] 15.1 | 5.2 / 2.4 |
| 2 | 37.4% | 61 | 2.9 [1.2, 5.9] 13.1 | 5.6 / 3.5 |
| 4 | 22.7% | 37 | 2.9 [1.5, 6.1] 11.1 | 6.3 / 4.9 |
| 6 | 14.7% | 24 | 3.2 [1.1, 4.4] 9.1 | 7.7 / 6.5 |

- depth into Deep = minutes past N3 onset the fire lands, on failure nights.
- nap sacrificed: `nonfail` = mean over non-failure nights; `all` = mean over all nights (failures count 0).

## [4] Tail concentration
Hard-swingers = within-subject SD >10 min = **8/42 (19%)**: Bidslab01, 08, 16, 17, 19, 47, 50, 53.
They hold **23% of nights** (even-spread baseline).

| margin | n_fail | % of failures from hard-swingers | from the rest |
|---|---|---|---|
| 0 | 87 | 26% | 74% |
| 2 | 61 | 30% | 70% |
| 4 | 37 | 43% | 57% |
| 6 | 24 | 58% | 42% |
