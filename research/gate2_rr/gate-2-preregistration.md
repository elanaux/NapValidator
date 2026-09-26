# Gate 2 — Pre-registration: does beat-to-beat (RR) data carry deep-sleep lead-time signal that averaged HR doesn't?

**Committed before any Gate 2 data has been downloaded, ingested, or scored.** Everything below is fixed now. Changes made after the baseline is seen (Step 3) must be logged as a dated amendment at the bottom of this file *before* the treatment arm runs. Nothing changes after the treatment is seen.

## Question

§9 closed the detector question on BidSleep: ~5 s averaged Apple-Watch HR hits a ~0.61 all-N3 AUROC ceiling for "next N3 onset within L", and RF ≈ logreg, so the limit is in the signal. Pass 3 found that true beat-to-beat HRV was **untestable** on BidSleep (5 s HR only). Gate 2 tests the counterfactual: **if real-time RR intervals were available, would they add lead-time signal beyond averaged HR?**

## Design — a within-dataset delta

- **Dataset:** PhysioNet CAP Sleep Database (fitness verified in Step 1 before any ingestion).
- **Baseline arm:** a 5 s averaged HR series derived from CAP ECG, run through the §9 harness **unchanged**. Features: `sd_60`, `drop_vs_base`, `slope_120` via `leadtime_harness.night_features`.
- **Treatment arm:** the same 3 baseline features **plus** a fixed set of RR/HRV features (below).
- Both arms use the same records, the same decision points (a **common row set**: rows where every feature in both arms is finite), the same subject-level folds, the same target, and the same classifiers.
- **The comparison is treatment minus baseline within CAP.** It is not a comparison to BidSleep's 0.61.

## Fixed protocol (inherited from `leadtime_harness.py` / `leadtime_shape_probe.py`)

| Item | Setting |
|---|---|
| CV | `GroupKFold(n_splits=5)`, grouped by subject; standardiser fit on train only |
| Classifiers | `LogisticRegression(max_iter=2000, class_weight="balanced")`; RF with the harness `RF_KW` (200 trees, depth 12, min leaf 50, `balanced_subsample`, seed 0) |
| Decision points | the end of each 5 s bin, after a 300 s warm-up; unscored / movement-time epochs dropped (harness `UNKNOWN` handling) |
| Stage mapping | R&K S3 ∪ S4 → N3. Onset = first N3 epoch after a non-N3 epoch (harness `onset_times`). Epoch length taken from the annotations (verified in Step 1) |
| Target | all-N3: non-N3 points, positive iff the next onset is ≤ L s away. first-N3-only: points before the first onset, positive iff that onset is ≤ L s away |
| Read points | L = 15 / 30 / 60 / 90 s |
| Causality | every feature is a trailing window ending at the decision point; no future samples |
| L = 0 | the concurrent N3-vs-rest classifier is computed and reported but **excluded** from the read, as in §9 |

## Ingestion rules (fixed now)

- **R-peaks:** `neurokit2.ecg_peaks` (default `neurokit` method) on the record's ECG channel, after `neurokit2.ecg_clean`.
- **RR QC** (applied identically for both arms):
  1. drop RR outside 300–2000 ms;
  2. drop an RR that deviates > 20 % from the median of the surrounding 11 RR (ectopic / missed-beat rule);
  3. report the % of beats removed per record.
- **Record exclusion:** > 20 % of beats removed, or an unusable / absent ECG channel. The threshold is set here, not after looking.
- **Baseline HR series:** instantaneous HR (60000 / NN) of the clean beats, averaged in non-overlapping 5 s bins timestamped at the bin end, **rounded to integer bpm** (matching BidSleep's integer, ~5 s HR). Bins with no clean beat are omitted, like BidSleep gaps. The baseline therefore uses the same QC as the treatment, so the delta isolates *information*, not cleaning.
- **Known mismatch, accepted:** BidSleep's cadence is irregular (2–9 s, median 5). CAP bins are a regular 5 s. This is not mimicked.

## Treatment feature set (fixed; no forward selection)

All features are trailing windows of clean NN intervals ending at the decision point. A window is valid only if clean beats cover ≥ 80 % of its duration.

| Feature | Definition |
|---|---|
| `ln_rmssd_60` | ln RMSSD over trailing 60 s (vagal / short-term) |
| `sdnn_300` | SD of NN over trailing 300 s (overall variability at the baseline window length) |
| `ln_hf_300` | ln HF power (0.15–0.40 Hz), trailing 300 s |
| `lf_hf_300` | ln(LF / HF), LF = 0.04–0.15 Hz, trailing 300 s |

Spectral features: NN series cubic-interpolated to 4 Hz, then Welch PSD (Hann, 128 s segments, 50 % overlap). The set is added all at once. Forward selection is **not** used: on the treatment arm it would be a tuning degree of freedom.

## PRE-REGISTERED BAR

**Primary metric (the gate).** all-N3, **logreg**. For each fold *k*, compute that fold's AUROC averaged over the 4 read-L values, then the **paired lift** Δₖ = AUROC_treatment,k − AUROC_baseline,k. That gives 5 paired Δs. The folds are identical across arms, so the pairing removes the between-fold difficulty variance that dominated §9's spread.

| Verdict | Condition |
|---|---|
| **PASS** | mean Δ ≥ **+0.04** **AND** Δₖ > 0 in **all 5** folds |
| **Clear FAIL** | mean Δ < **+0.02**, **OR** Δₖ ≤ 0 in **≥ 2** of 5 folds |
| **INCONCLUSIVE** | anything else (e.g. mean Δ in [0.02, 0.04) with ≤ 1 non-positive fold, or mean ≥ 0.04 with exactly one non-positive fold) — reported as inconclusive and not rounded to either side |

**What PASS means (Amendment 1).** PASS means **"RR carries lead-time signal beyond averaged HR → proceed to MESA."** PASS is **NOT a usefulness claim.** The lift is the only gate; there is no absolute-AUROC requirement. The absolute usefulness bar will be pre-registered separately, **before MESA data is accessed**. Absolute AUROC is still reported here, as non-gating.

**RF paired-lift arm (Amendment 2).** LR remains the gate. RF lift Δᴿᶠₖ = AUROC_RF-treatment,k − AUROC_RF-baseline,k is computed on the same folds and scored against the same bar (mean ≥ +0.04 **and** Δᴿᶠₖ > 0 in all 5 folds). **If RF meets that bar and LR does not, the verdict is "INCONCLUSIVE — nonlinear signal."** That verdict routes to MESA and is **not** a pass. If LR passes, the verdict is PASS regardless of RF (RF reported).

**Noise floor and sample size (Amendment 3).** The +0.02 noise floor was calibrated on BidSleep (45 usable subjects of 47). CAP is smaller and differently composed, so **the CAP verdict is directional by construction; MESA is the deciding run.** The usable CAP subject count from Step 1 is recorded next to the verdict when it is reported.

**Why these numbers.** Pass 2's bar (mean ≥ 0.65) sat **+0.04** above the 0.61 ceiling; that distance was the pre-registered definition of "climbing toward useful", so +0.04 is the same bar expressed as a lift. The "every fold improves" clause is the paired analogue of pass 2's per-fold-min clause: the lift must be consistent across held-out subject groups, not carried by one fold. The +0.02 fail line is roughly the size of the RF-vs-logreg differences seen throughout §9 (0.01–0.02), i.e. noise-scale on this harness.

**Reported, not gating:**
- Per-read-L Δ (15/30/60/90) and per-fold AUROC for both arms; AUPRC and prevalence.
- first-N3-only, both arms (informational, as in §9).
- **RF on both arms. Does the signal-limited pattern persist?** The pattern is judged **broken** if on the treatment arm RF − logreg ≥ **+0.03** (mean over folds) with RF ahead in ≥ 4 of 5 folds. Otherwise it **persists**. (Reported only. The RF *lift* arm above is what can produce "INCONCLUSIVE — nonlinear signal".)
- The treatment arm's absolute AUROC against the original 0.65 / 0.60 bar. This is informational only, because it crosses datasets.

## Comparability stop (Step 3)

The CAP baseline arm (logreg, all-N3, avg over read-L) is expected near BidSleep's 0.61. **If its mean falls outside [0.53, 0.69]** (BidSleep's per-fold envelope 0.55–0.67, ±0.02), STOP. That's a population or derivation difference to discuss, not something to tune.

## What a result can and can't mean (stated before the result)

- **ECG-derived RR is an upper bound** on wrist PPG. PPG inter-beat intervals are noisier, motion-sensitive, and (per §9 pass 6) not streamable to third parties on Apple Watch today. A PASS says the information exists in the heartbeat. It does not say a watch app can get it.
- **CAP is small and mostly pathological** (NFLE, RBD, PLM, insomnia, etc.; healthy controls a minority). The pathology mix is characterised in Step 1. Pathology can shift both HRV and N3 architecture. In particular, RBD, PLM and narcolepsy (36/105 usable subjects) alter autonomic function and HRV directly, which affects the RR features specifically, not just sleep depth (Amendment 4). The CAP verdict remains directional; MESA decides.
- **Overnight, not naps**, same as BidSleep.
- A **FAIL** on this upper-bound signal would strengthen §9's conclusion: if clean ECG RR can't move the needle, wrist PPG won't.

## Amendments

**2026-09-26 — Amendments 1–3, made before Step 1 (no CAP data downloaded or seen).** At the owner's review of the initial pre-registration:
1. Verdict semantics: PASS = "RR carries signal beyond averaged HR → proceed to MESA", explicitly not a usefulness claim; the usefulness bar is to be pre-registered separately before MESA access.
2. Added the RF paired-lift arm with the same bar; RF-only success → "INCONCLUSIVE — nonlinear signal", routes to MESA, not a pass.
3. Added the note that the +0.02 floor is BidSleep-calibrated, the CAP verdict is directional, MESA decides, and the usable CAP subject count is recorded with the verdict.

**2026-09-26 — Amendment 4, made after Step 1 fit-verification (metadata only: EDF headers + hypnograms; no ECG signal ingested, no features or AUROC computed).** Evidence in `fit_verify_cap.py` / `cap_fit_table.csv`.

*Record exclusions (108 → 105 usable before the beat-removal rule):*
- `n16`: no ECG channel.
- `rbd11`: byte-identical EDF to `rbd10` (same SHA256 in PhysioNet `SHA256SUMS.txt`; the demographics sheet also lists identical sex and age). One recording, so keeping both would leak one night across folds. `rbd10` is kept.
- `nfle27`: clock contradiction. The hypnogram starts at 22:08:16, 48 min **before** the EDF start (22:56:40). Alignment can't be trusted.

*Alignment rule:* CAP hypnogram and EDF share one clock (in 86/108 records the scoring ends within ~5 min of the EDF end, median 0 s). Epochs are placed by clock time relative to the EDF start, rolling past midnight. No per-night offset search (unlike BidSleep). **Epochs falling wholly or partly outside the recording are trimmed** (18–138 s overruns in ~20 records). For `n13`/`n14` (EDF header `n_records = -1`) the duration is taken from file size.

*ECG channel:* the ECG/EKG-labelled channel. Where ECG1 and ECG2 are stored separately (`nfle25`, `nfle33`), the lead is ECG1 − ECG2.

*Sampling rate (Option A):* all usable records are kept regardless of ECG sampling rate. 20 records are at 100–128 Hz, where R-peak timing is quantised to 8–10 ms; R-peak times are refined by **parabolic interpolation** on the cleaned ECG for all records.
- **The primary verdict is computed on all usable subjects** (105 before the > 20 % beat-removal exclusion; the post-exclusion count is recorded at ingestion).
- **≥ 200 Hz sensitivity rerun (non-gating):** the full protocol re-run on the subset of usable subjects whose ECG is ≥ 200 Hz, with its own `GroupKFold(5)`. Its role:
  - If the subset's LR lift meets the PASS bar (mean Δ ≥ +0.04 **and** Δₖ > 0 in all 5 subset folds) while the primary verdict is FAIL or INCONCLUSIVE, the verdict becomes **"INCONCLUSIVE — possible sampling-rate attenuation"**, which routes to MESA.
  - It can **never** produce a PASS, and it **cannot** downgrade a primary PASS.
  - The subset lift is reported alongside the primary whatever the outcome.

*Added caveat:* RBD, PLM and narcolepsy (36 of 105 usable subjects) alter autonomic function and HRV directly. That affects the RR features specifically, not just sleep depth. The CAP verdict remains directional; MESA decides.

**2026-09-26 — Amendment 5, made before any ECG signal was downloaded or processed.** Two ingestion rules turned out to be under-specified or inconsistent while the ingestion code was being written:
- **Ectopic rule made causal.** The original rule ("> 20 % from the median of the *surrounding* 11 RR") uses up to ~5 future beats, which contradicts the pre-registered causality requirement ("features must be causal … no future leakage"). Causality takes precedence. **Revised:** drop an RR that deviates > 20 % from the median of the **preceding 11** in-range RR, which is also what a real-time device could compute. It applies identically to both arms.
- **Exclusion basis made explicit.** "> 20 % of beats removed" is computed over the **scored window** (the span that produces decision points), because some recordings extend hours outside scoring (up to 15 h) with electrode-off stretches that don't enter the analysis. The whole-recording % is reported alongside.
- **Implementation notes** (not rule changes): EDFs are streamed and only the ECG channel is kept (the full files total ~42 GB and the disk can't hold them). The stage codes match the harness: W 0, S1 1, S2 2, S3|S4 3, REM 4, MT/unscored/hypnogram gaps 5 (UNKNOWN). The 5 s grid is anchored at the EDF start.

*(any further pre-treatment amendment is dated and justified here)*
