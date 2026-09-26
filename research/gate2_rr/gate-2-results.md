# Gate 2 — Results: does beat-to-beat (RR) data carry lead-time signal beyond averaged HR?

**Verdict (pre-registered, all-N3, logreg paired lift): INCONCLUSIVE.** Usable CAP subjects: **90** (of 108 records; 105 after the Step 1 exclusions, 90 after the > 20 % beat-removal rule).

The pre-registration and its six dated amendments are in `gate-2-preregistration.md`. They were committed before the data each one governs was seen (the final pre-treatment commit is `a7dfb11`). Nothing was retuned after the treatment results. Every number below is copied from `treatment_cap_stdout.txt` (Step 4) and `baseline_cap_stdout.txt` (Step 3).

## 1. The gate

Paired lift Δ = treatment − baseline AUROC, per subject-level fold, averaged over L = 15/30/60/90 s, on the common row set (494,395 decision points; 92.6 % of baseline-valid rows).

| Arm | Fold 1 | Fold 2 | Fold 3 | Fold 4 | Fold 5 | Mean | Positive | Bar result |
|---|---|---|---|---|---|---|---|---|
| **LR lift (gate)** | +0.040 | **−0.026** | +0.037 | +0.030 | +0.040 | **+0.024** | 4/5 | **INCONCLUSIVE** |
| RF lift | +0.013 | −0.002 | +0.015 | +0.025 | −0.002 | +0.010 | 3/5 | does not meet bar |
| ≥ 200 Hz LR lift (75 subj, non-gating) | +0.038 | +0.026 | +0.025 | +0.031 | −0.003 | +0.023 | 4/5 | does not meet bar |

The bar: PASS if mean ≥ +0.04 and all 5 folds positive. FAIL if mean < +0.02 or ≥ 2 folds non-positive. Anything else is INCONCLUSIVE.

- LR clears the fail line (+0.024 ≥ +0.02, only one negative fold) but misses the pass line on both counts: the mean is short of +0.04, and fold 2 is negative.
- The RF lift doesn't meet the bar, so this is **not** "INCONCLUSIVE — nonlinear signal".
- The ≥ 200 Hz subset doesn't meet the bar, so this is **not** "possible sampling-rate attenuation". The subset lift (+0.023) is essentially the primary lift (+0.024), so low-rate ECG isn't hiding the signal.
- The pre-registration doesn't say where a plain INCONCLUSIVE routes. Only PASS and the two labelled INCONCLUSIVE variants route to MESA. **Routing is the owner's call.**

### Per read-L (all-N3, primary)

| L (s) | LR base | LR treat | LR Δ | RF base | RF treat | RF Δ | AUPRC LR b/t |
|---|---|---|---|---|---|---|---|
| 15 | 0.638 | 0.662 | +0.023 | 0.672 | 0.681 | +0.009 | 0.010 / 0.011 |
| 30 | 0.634 | 0.658 | +0.024 | 0.670 | 0.677 | +0.007 | 0.019 / 0.022 |
| 60 | 0.628 | 0.653 | +0.025 | 0.663 | 0.673 | +0.009 | 0.036 / 0.040 |
| 90 | 0.622 | 0.647 | +0.025 | 0.657 | 0.671 | +0.013 | 0.051 / 0.056 |

The LR lift is flat across L (+0.023 to +0.025). Like the baseline, it isn't a signal that grows as onset approaches.

## 2. RF vs LR on the treatment arm (does the signal-limited pattern persist?)

- **Amendment 6 rule: persists with respect to RR.** The RF − LR gap *shrinks* from +0.035 (baseline) to +0.020 (treatment). The growth is −0.027 / +0.023 / −0.022 / −0.005 / −0.042 (mean −0.015; growing in 1/5 folds).
- **Treatment LR (0.655) is still below baseline RF on averaged HR alone (0.666).** Over what a nonlinear model already extracts from averaged HR, RR adds +0.010 (RF lift), positive in 3/5 folds. Read plainly: a good part of the LR lift may be RR handing the linear model information that RF already recovers nonlinearly from the 5 s HR. This is an interpretation of the numbers above, not a new test.

## 3. Informational (non-gating)

- **first-N3-only:** LR Δ −0.010 (1/5 positive); RF Δ +0.024 (4/5 positive). Noisy (48k points; per-fold Δ from −0.082 to +0.091).
- **L = 0 concurrent N3-vs-rest (excluded from the read):** LR 0.705 → 0.767 (+0.062). RR carries noticeably more *current-state* information than *lead-time* information. It helps tell you are in N3, not that N3 is coming.
- **Absolute** (cross-dataset 0.65 / 0.60 bar, informational): treatment LR mean 0.655, fold-min 0.643. AUPRC stays at 0.011–0.056 against prevalence of 0.6–3.4 %.
- **Fold 2** is the only negative LR fold. Its common-row baseline (0.695) is the highest of the five; the treatment brings it to 0.669. Not investigated (no new analyses).
- The common-row baseline (LR 0.631) differs slightly from the Step 3 baseline (0.641, all baseline-valid rows). The row set changes, and GroupKFold reassigns subjects to folds by group size. The gate uses the common-row pairing as pre-registered.

## 4. Logged findings (non-gating, no new analyses)

- **The CAP averaged-HR baseline breaks "RF ≈ LR".** CAP: LR 0.641, RF 0.676, RF > LR in 5/5 folds (Step 3). BidSleep: LR 0.61, RF 0.59–0.60 (§9). Candidate explanations are untested: (a) cleaner labels (CAP's shared-clock alignment vs BidSleep's per-night offset search) and (b) cohort heterogeneity (ages 14–82, 8 conditions). This bears on §9's "signal-limited, not model-limited" claim. On CAP, model capacity *does* add ~+0.035 on averaged HR. Resolution deferred to MESA.
- **Exclusion skew by sampling rate:** 5/20 records < 200 Hz were dropped by the beat-removal rule (n6, nfle11, sdb1, sdb2, sdb4) vs 10/85 at ≥ 200 Hz.
- **The 20 % beat-removal rule removes real physiology.** In 3/4 SDB records (sdb1, sdb2, sdb4) and nfle11, the removed beats are smooth, near-median deviations (apnea-type cyclic HR swings), not missed or double detections. The same filter trims large genuine swings inside retained records, and the RR features are computed on the trimmed NN. This is a conservative bias against the RR arm. **Flag for MESA design.**

## 5. Caveats

- **ECG-derived RR is an UPPER BOUND** on what a wrist PPG sensor would give. PPG inter-beat intervals are noisier and motion-sensitive, and (§9 pass 6) not streamable to third-party apps on Apple Watch today. A lift of +0.024 on clean ECG would be expected to shrink on PPG.
- **CAP is small and largely pathological.** 90 usable subjects; 15 healthy controls originally, 13 after exclusions. RBD, PLM and narcolepsy (36/105 before the beat rule) alter autonomic function and HRV directly, which affects the RR features specifically. **The CAP verdict is directional by construction; MESA is the deciding run.** The +0.02 noise floor was calibrated on BidSleep (45 usable subjects).
- **Overnight data, not naps.**
- The 5 s HR is a regular grid; BidSleep's Apple Watch HR is irregular (2–9 s). Accepted mismatch.

## 6. Carry forward to the MESA pre-registration (not acted on)

- The absolute **usefulness bar should be on AUPRC or precision at an operating point, not AUROC**. At 0.6–3.4 % prevalence, AUROC in the 0.6s coexists with AUPRC around 0.01–0.06.
- Revisit the ectopic/artifact rule so it doesn't remove genuine physiological variability (see §4).
- Resolve why RF > LR on CAP's averaged HR (alignment vs heterogeneity) before re-using "RF ≈ LR" as evidence of a signal ceiling.
- Pre-specify where a plain INCONCLUSIVE routes.

## Artifacts

`gate-2-preregistration.md` · `fit_verify_cap.py` / `cap_fit_table.csv` (Step 1) · `ingest_cap.py` / `cap_ingest_qc.csv` (Step 2) · `run_baseline_cap.py` / `baseline_cap_stdout.txt` (Step 3) · `run_treatment_cap.py` / `treatment_cap_stdout.txt` (Steps 4–5). Raw and derived PhysioNet data live in the gitignored `cap_raw/` and `cap_derived/`. The EDFs were streamed from PhysioNet's AWS open-data mirror, SHA256-verified against PhysioNet's `SHA256SUMS.txt`. neurokit2 is pinned at 0.2.11 (Python 3.9 venv).
