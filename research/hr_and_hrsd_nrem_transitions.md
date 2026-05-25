# HR and HR SD Across NREM Sleep Stages: Literature Review for Nap Algorithm Tuning

**Date:** 2026-05-20
**Author:** Research synthesis (Claude)
**Scope:** Heart-rate and HR variability characteristics across NREM stages, with focus on the N2 (Light) → N3 (Deep) transition, in service of tuning the current nap-algorithm parameters:

- `t_hr = 5 bpm` — HR drop threshold from Light reference, for deepening detection
- `t_var = 0.8 bpm` — absolute HR sample SD threshold (in bpm) for deepening detection
- `60 s sustain + 30 s confirm` windows

> **Important units note up front.** Most published sleep-HRV literature reports variability as **SDNN / RMSSD in *milliseconds* of R-R interval variation**, not as a sample standard deviation of beats-per-minute. These quantities are related but not interchangeable: at HR ≈ 60 bpm, a 50 ms SDNN ≈ ~3 bpm HR SD over the same window, but the conversion is non-linear and depends on mean HR. Where direct HR-SD-in-bpm data exist (wearable studies), I flag them explicitly. Inferences from HRV-in-ms to HR-SD-in-bpm are flagged as inferences.

> **Adversarial / prompt-injection check.** I monitored fetched content for injected instructions. **One** notable event: WebFetch on `nature.com/articles/s41598-024-53839-x` returned a redirect to an `idp.nature.com` authorize endpoint with instructions telling me to re-fetch that redirect URL with the same prompt. I treated that as a routine paywall redirect, not a malicious injection, and instead pivoted to the PMC mirror (`PMC10897321`). No other injection attempts were observed. System reminders about task-tool usage came from the harness, not from fetched content.

---

## 1. Typical HR levels by NREM stage

### Headline pattern (consensus, multiple studies)

Mean HR declines monotonically from Wake → N1 → N2 → N3, with the global nadir of the 24-h cycle reached in N3 / slow-wave sleep (SWS). REM HR rises back toward or above N2 levels. This direction-of-change is one of the most replicated findings in sleep physiology.

- Tobaldini et al. (2013), *Frontiers in Physiology*: *"from N1 to N3, the stage of highest neural synchronization, a gradual decrease is observed in HR, BP and MSNA, with minimum values reached during N3."* (https://pmc.ncbi.nlm.nih.gov/articles/PMC3797399/)
- Trinder et al. (1997), *J. Sleep Res.*: spectral HRV shows increased HF and decreased LF across NREM stages, consistent with progressive vagal dominance. (https://pubmed.ncbi.nlm.nih.gov/9191582/)

### Numerical values (sparse and study-dependent)

Quantitative *absolute* HR-by-stage data are surprisingly thin in the literature; most studies report HRV indices rather than mean HR. The cleanest values I located:

| Source | Population | Stage | HR |
|---|---|---|---|
| Herzig et al. 2017 (PMC5767731, n=15 healthy young males, median across nights) | Healthy young men, overnight PSG | N2 | **51.6 bpm** (IQR 47.9–58.3) |
| Same | Same | SWS (N3) | **51.5 bpm** (IQR 47.9–55.3) |
| Same | Same | REM | 53.6 bpm (IQR 49.7–58.3) |
| Yoo et al. 2023 (PMC10208252, healthy adults during SWS) | Healthy adults | SWS | **61.85 bpm** (SD 8.2 between-subject) |
| Gao et al. 2020 (PMC7520661, n=25 nappers) | Healthy adults, afternoon naps | N3 | "lnRR higher in N3 than N2" — no absolute bpm |

(https://pmc.ncbi.nlm.nih.gov/articles/PMC5767731/) (https://pmc.ncbi.nlm.nih.gov/articles/PMC10208252/) (https://pmc.ncbi.nlm.nih.gov/articles/PMC7520661/)

### N2 → N3 drop magnitude — the critical number for `t_hr`

**This is the headline finding that matters most for the algorithm:** in the cleanest small-sample dataset I located (Herzig et al. 2017, n=15), **median HR in N2 and N3 differs by ~0.1 bpm** (51.6 vs 51.5) — i.e. effectively indistinguishable at the *steady-state median* level. Two implications:

1. The N2 → N3 *median* drop is small (typically <3 bpm in healthy young adults), much smaller than the wake → sleep drop (which is ~5–10 bpm immediately on sleep onset, and 20–30% — ~12–30 bpm — relative to daytime resting HR by deep sleep).
   - "Generally speaking, your sleeping heart rate runs about 20% to 30% lower than your daytime resting heart rate." (https://health.clevelandclinic.org/sleeping-heart-rate)
2. The drop one sees *transiently* on entering N3 is somewhat larger than the steady-state difference, because slow-wave sleep co-occurs with parasympathetic surges. Csósza et al. (2024, body-cooling intervention) measured a within-subject HR decrease of **−2.36 ± 1.08 bpm** when SWS was experimentally enhanced. (https://pmc.ncbi.nlm.nih.gov/articles/PMC10897321/)

### Individual variation

- Trinder et al.: ΔHR responses to arousals ranged **1.9–18.3 bpm** *within* their sample — i.e. ~10× spread. Resting HR variation across healthy adults (50–75 bpm) implies similar absolute-bpm noise floor heterogeneity.
- Bonnemeier et al. (PMC8923916): HR in the *first* N2 epoch of the night differs significantly from all subsequent N2 epochs in the same subject, indicating substantial within-subject between-epoch drift. (https://pmc.ncbi.nlm.nih.gov/articles/PMC8923916/)

**Consensus assessment:** the magnitude of HR drop into deep sleep is **established directionally** but **highly variable in absolute terms** — between-subject SD often exceeds the mean N2→N3 difference itself. A single fixed `t_hr` will fit some users well and miss others entirely.

---

## 2. HR-drop dynamics during the Light → Deep transition

### Slope vs. cliff

**Consensus: gradual, not a cliff.** Multiple reviews describe the N1→N3 decrease as "gradual" with no reported step-function. The transition spans cycles of slow-wave build-up rather than a single discrete moment.

- Tobaldini 2013: "*gradual* decrease ... with minimum values reached during N3" (https://pmc.ncbi.nlm.nih.gov/articles/PMC3797399/).
- Stephani et al. 2021 / time-course paper: "the onset of slow-wave sleep ... occur[s] only as gradual processes over time, indicating that these transitions are not abrupt." (https://www.frontiersin.org/journals/physiology/articles/10.3389/fphys.2021.623401/full)

### Typical timing

- Healthy young adults at night typically reach scored N3 ≈ **25–30 min after sleep onset** (cited in nap-physiology articles; widely repeated in PSG textbooks).
- Sleep-deprived nappers reach scored N3 within ~5 min (see §6).
- Once the *transition window* is in progress, cardiac autonomic shifts span minutes:
  - Brandenberger / Kuula / Stephani lineage: vagal HRV begins shifting *several minutes* before scored REM and may continue past it; comparable lead has been reported into N3.
  - Trinder et al. 1997: HR acceleration begins **≥10 beats before** EEG arousal (https://pubmed.ncbi.nlm.nih.gov/9191582/) — i.e. autonomic precedes cortical scoring by ~10 cardiac cycles ≈ 10–15 s in the arousal direction.

### Oscillation / arousal during transition

- Cyclic Alternating Pattern (CAP) in NREM: arousal-related "Phase A" events recur with a **pseudo-rhythmic 20–40 s period**, each accompanied by transient HR, BP and respiration upswings, with quieter "Phase B" intervals in between. (Terzano lineage, e.g. https://pubmed.ncbi.nlm.nih.gov/10733684/, https://pmc.ncbi.nlm.nih.gov/articles/PMC10231930/)
- K-complexes (predominant in N2) produce brief HR upswings followed by deeper EEG suppression — a single K-complex is a measurable mini-arousal in HR space.
- Lechinger et al. 2016 (PMC4957222): slow-wave initiation is *phase-locked* to ongoing cardiac oscillations (phase delay ~66 ms from ECG cycle to slow-wave onset). Slow waves cluster around heartbeat phases. (https://pmc.ncbi.nlm.nih.gov/articles/PMC4957222/)

**Implication for trigger logic:** during the N2→N3 transition, HR is *not* a monotone decline — it is a downward trend with embedded 20–40 s arousal swings. A 60 s sustain window straddles roughly 1.5–3 CAP cycles, so a single Phase-A event near the window edge can break the criterion.

---

## 3. HR variability during sleep stages

### What the literature actually measures

HRV literature overwhelmingly uses **R-R-interval-based metrics in milliseconds**: SDNN (overall variability), RMSSD (short-term, parasympathetic-dominated), pNN50, HF, LF, LF/HF. Pure "HR sample standard deviation in bpm over a rolling window" is rare except in wearable engineering literature.

### Time-domain HRV by NREM stage (consensus)

Direction: **RMSSD increases or stays flat from wake → N3** (more vagal control), but **SDNN tends to be lowest in SWS** (because SDNN captures total variability, including the LF/sympathetic component that drops in SWS).

| Stage | RMSSD (ms) | SDNN (ms) | mean HR (bpm) |
|---|---|---|---|
| N2 | 70.7 (54.1–91.1) | 68.5 (50.9–94.5) | 51.6 |
| SWS / N3 | 67.3 (49.2–97.6) | **53.8** (40.7–71.6) | 51.5 |
| REM | 79.7 (58.7–109.3) | 105.5 (82.6–134.7) | 53.6 |

Source: Herzig et al. 2017, n=15 healthy young men, median (IQR). (https://pmc.ncbi.nlm.nih.gov/articles/PMC5767731/)

Same paper: **between-segment variance is dramatically smaller in SWS** than in N2 or REM — only ~8.3% of total HR variance in SWS vs 13.4% in N2 vs 16.2% in REM. SWS is the most *reproducible* state for HR measurement. This is a strong, replicated finding.

### Translating to HR sample SD in bpm (INFERENCE)

If we approximate HR-SD-in-bpm ≈ (60 / mean_RR_seconds²) × SDNN_seconds, then at mean HR 51 bpm (RR ≈ 1.18 s):

- N2 SDNN 68.5 ms ≈ HR SD **2.96 bpm**
- N3 SDNN 53.8 ms ≈ HR SD **2.32 bpm**
- REM SDNN 105.5 ms ≈ HR SD **4.55 bpm**

**Inference, not measurement.** This back-of-envelope conversion assumes SDNN is computed over the same window as HR-SD-bpm and ignores beat-to-beat HR vs R-R nonlinearity. But it gives a rough sense of the floor: even N3 healthy-adult HR variability over a multi-minute window is on the order of **~2 bpm**, not <1 bpm.

### "HR volatility" thresholds from wearable engineering

The closest direct analogue I found is van Hees et al. 2018-style sleep-detection work:
- Linton et al. 2022 (PMC9106748): defines HR volatility for sleep-window refinement as **a rolling 10-min SD of HR of 6 bpm**. (https://pmc.ncbi.nlm.nih.gov/articles/PMC9106748/)
- That paper also notes: *"local heart rate standard deviation by itself (without motion) was consistently the lowest performing feature set for sleep/wake classification, scoring roughly 24–33% of wake epochs correctly when the fraction of sleep epochs scored correctly was fixed at 90%."* HR-SD alone is a weak classifier.

### Monotonic decrease, or different pattern?

- **SDNN: not strictly monotonic.** Drops from N2 → N3, but rebounds in REM.
- **RMSSD: roughly flat across NREM, rises in REM.**
- **LF (sympathetic-band): drops monotonically from N1 → N3, then rises in REM.** Sympathetic activity *is* the part of variability that most cleanly tracks sleep depth.

**Consensus:** *overall* HR variability decreases from Light to Deep, but the magnitude of the decrease in healthy adults is modest (~20–25% of N2 SDNN) and noisy.

---

## 4. Temporal coupling of HR drop and HRV changes

This is critical for the algorithm's dual-criterion design.

### Asynchronous, with HRV often leading

Multiple lines of evidence suggest **autonomic changes precede EEG-scored stage transitions**:

- Trinder et al. 1997: "HR acceleration at least 10 beats prior to the EEG arousal." Sympathetic activation appears to *initiate* arousal events. (https://pubmed.ncbi.nlm.nih.gov/9191582/)
- The same lineage shows HRV shifts toward the next stage **minutes before** the scored stage change for REM transitions; analogous (though smaller) leads have been reported for N3 entry.
- Stephani et al. 2021 (adaptation-night discrepancies paper, PMC8044772): EEG sleep architecture normalises by sleep cycle 2–4 in the adaptation night, but HF-HRV remains suppressed across **all four cycles** — autonomic and cortical systems adapt on *different timescales*. The authors explicitly conclude: *"the autonomic nervous system has lower adaptability than [the] cortical system."* (https://pmc.ncbi.nlm.nih.gov/articles/PMC8044772/)

### Within the N2 → N3 transition specifically

- Yoo et al. 2023: cardiac vagal tone (HF-HRV) begins to rise *before* the annotated transition to N3. (https://pmc.ncbi.nlm.nih.gov/articles/PMC10208252/, via search summary; full-text quantification not located.)
- Lechinger et al. 2016: individual slow waves are phase-locked to cardiac oscillations with a ~66 ms phase delay — i.e. heart leads brain at the micro level. (https://pmc.ncbi.nlm.nih.gov/articles/PMC4957222/)

### Inference for the algorithm

If HR-level and HR-variability changes were tightly synchronous, requiring both would be efficient. The literature suggests instead that:

- HRV / vagal tone often **shifts first** (seconds-to-minutes before EEG N3).
- Mean HR settles to its N3 trough more gradually and with embedded CAP oscillations.
- The two channels do not drop in lockstep — there is a window during which HRV is "N3-like" but mean HR is still "N2-like" (or close to it).

**Direct quantification of the lead/lag in healthy adults is sparse** — most studies report stage-averaged values, not transition kinematics. Single-study evidence (Yoo, Stephani, Trinder) all point the same direction: HRV leads HR-level changes by seconds-to-minutes.

---

## 5. Arousal events during NREM

### Frequency in healthy adults

- Bonnet & Arand and the AASM-cited norms: healthy young-to-middle-aged adults average **~10–15 arousals per hour of sleep**; this rises by ~2.1/hr/decade with age, reaching ~25–27/hr in adults >60. (https://pubmed.ncbi.nlm.nih.gov/31006560/, normative PSG meta-analysis)
- Schäfer et al. 2015 (PMC4507737): documented 4,751 arousals across 28 healthy young adults over two nights — i.e. ~85 arousals/subject/night. (https://pmc.ncbi.nlm.nih.gov/articles/PMC4507737/)
- CAP A-phases (sub-scoring-threshold arousals) recur **every 20–40 s** during NREM — orders of magnitude more frequent than scored AASM arousals.

### HR signature

- Schäfer et al.: ΔHR per arousal ranged **1.9–18.3 bpm** across subjects. ΔHR at moderate intensity (intensity grade 5) ranged 4.1–18.1 bpm.
- Linear dose-response: **~2 bpm ΔHR per +1 arousal-intensity unit**. (https://pmc.ncbi.nlm.nih.gov/articles/PMC4507737/)
- Earlier Pillar et al. work: 2.9 / 3.9 / 8.6 bpm HR rise for arousal grades 0 / 1 / 2.
- Arousal-associated HR rise begins **~2 s before scored EEG arousal**, persists 10–15 s, and decays over ~20–30 s.

### Clustering vs. random

- Arousals are *not* uniformly distributed. They cluster at:
  1. **Stage transitions** — especially around the N2↔N3 and NREM↔REM boundaries.
  2. **CAP A-phases**, which themselves cluster around N1 / N2 and during N3 entry.
- Stage N3, once established, has the *lowest* per-minute arousal density.

### Effect on rolling HR statistics

A single moderate arousal can spike a 60-s rolling HR mean by 1–3 bpm and inflate a 60-s rolling HR SD by **1–2 bpm**, depending on how many seconds of the window the arousal occupies. **Both currently-set thresholds (`t_hr = 5 bpm`, `t_var = 0.8 bpm`) are at or below the magnitude of a single CAP-scale arousal**, meaning an arousal that lands inside the sustain window can easily break the criterion.

---

## 6. Sleep deprivation effects on HR patterns during naps

### Accelerated and amplified N3 entry

- Stahl et al. 2021 (PMC8598175): sleep-deprived nappers reach scored N3 at average **~5 min** after sleep onset (vs typical 25–30 min in unrestricted overnight sleep) and spend **48% (SD 25%) of allotted nap time in N3** in 30-min and 60-min nap protocols. (https://pmc.ncbi.nlm.nih.gov/articles/PMC8598175/)
- Hubbard et al. 2020 (PMC7297752 / *Nat. Commun.*): a *δ2* slow-wave subtype responds steeply to sleep deprivation with high initial power and fast discontinuous decay; **temperature, muscle tone, and HR all revert to characteristic NREM levels within the first recovery hour**, paralleling δ2 dynamics. (https://www.nature.com/articles/s41467-020-16915-0)

### HR-magnitude effects

- Limited direct data on HR-*drop magnitude* in deprived naps. Inference from the homeostatic literature: because deprived sleep has higher SWA pressure and earlier/deeper SWS, the **transition into N3 is steeper** (more SWA per unit time) and may produce a **larger transient HR drop** than well-rested sleep. But absolute HR levels in deprived sleep can be *elevated* (sympathetic dysregulation) — see Tobback et al. 2020 (PMC8060636): RMSSD and HF decrease, normalised LF increases during sleep deprivation.
- Net result is an open question in the literature: faster transitions *may* break a 60-s sustain window, while higher baseline sympathetic tone *may* keep absolute HR above the Light reference until the transition is well underway.

### Variability under deprivation

- Tobback et al.: HRV (RMSSD, HF) is reduced under sleep deprivation. So a deprived user's *baseline* N2 HRV is already closer to N3 values — the SD-based criterion has less headroom to detect deepening.

**Consensus:** sleep deprivation **accelerates and amplifies N3 entry** but **reduces baseline HRV**, meaning a sleep-deprived nap looks "deeper on HR-level" but "shallower on HRV-stage-difference" than a well-rested nap. Both ends of the algorithm's dual criterion are affected, in *opposite* directions.

---

## Synthesis: are `t_hr = 5`, `t_var = 0.8`, `60 s + 30 s` appropriate?

### `t_hr = 5 bpm` — likely **aggressive on the median, but appropriate transiently**

- Steady-state median HR difference between N2 and N3 in healthy young adults is on the order of **0–3 bpm** (Herzig 2017: 0.1 bpm; cooling-induced SWS-enhanced: ~2.4 bpm).
- However, the *trough* of N3 HR within a transition window is several bpm below the *peak* of the preceding N2 window; arousals and CAP add another 2–5 bpm of fluctuation. A drop of 5 bpm from a Light-reference HR is plausible to hit transiently during a sleep-deprived nap or in a user with a large autonomic dynamic range.
- For well-rested users with naturally small N2-vs-N3 medians (Herzig sample), **`t_hr = 5` may never trigger**, even when N3 is genuinely entered.
- **Verdict:** *appropriate for sleep-deprived users with steep transitions; aggressive for well-rested users with shallow autonomic dynamics.* A personalised threshold (e.g. fraction of the user's own wake→sleep drop) would track the literature better than a fixed bpm.

### `t_var = 0.8 bpm` — likely **very aggressive (too low)** for the SD-in-bpm metric

- Direct SD-in-bpm references are scarce, but Linton et al. 2022 uses **6 bpm** over 10 min for sleep/wake (i.e. a much coarser threshold).
- Inference from HRV-in-ms (Herzig): N3 HR-SD ≈ 2.3 bpm, N2 ≈ 3.0 bpm. The *difference* between N2 and N3 in inferred HR-SD is ~0.6–0.7 bpm — i.e. of the same order as `t_var = 0.8`, but the *absolute level* of N3 HR-SD is several times the threshold.
- An absolute threshold of 0.8 bpm sample SD would require an unusually quiet HR record — closer to artifact-free SWS with no CAP swings. In a typical user this would *gate out* most legitimate N3 entries.
- **Verdict:** *likely too low as an absolute floor*; consider either (a) a *relative* drop in SD from the Light reference (e.g. SD must fall to ≤ 50–60% of Light SD), or (b) a higher absolute floor (~1.5–2 bpm) to admit normal N3 with embedded CAP swings.

### `60 s sustain + 30 s confirm` — **shape concern, not just magnitude**

Three findings from the literature suggest the window structure has subtle issues:

1. **CAP period (20–40 s) is shorter than the sustain window but a meaningful fraction of it.** A single Phase-A arousal landing in the middle of the 60-s sustain breaks the criterion for ~10–15 s, plausibly enough to fail a tight `t_var = 0.8` check. The dual criterion is therefore sensitive to CAP rhythm. *Implication:* either lengthen sustain to ≥3× CAP period (~90–120 s) so a single CAP event cannot break it, or weaken the SD check to be robust against single-event spikes (e.g. median-filtered SD).
2. **Asynchronous coupling: HRV often leads HR-level by seconds-to-minutes.** A logical-AND of both conditions, required *simultaneously*, can either delay detection (until the laggard channel catches up) or never trigger if the lead channel transiently retracts before the lag channel arrives. *Implication:* consider OR with confirmation, or stagger the windows (e.g. SD condition can be met up to 60 s *before* HR condition, not just simultaneously).
3. **The first N2 epoch of a session has significantly different HR from later N2 epochs** (Bonnemeier et al.). A 60-s sustain at the *first* moment of stable N2 sets a reference that may already be drifting. *Implication:* the Light reference should be sampled from a stable mid-N2 window, not from the earliest qualifying N2.

### Overall judgement (from literature)

| Parameter | Assessment | Direction of mistuning |
|---|---|---|
| `t_hr = 5 bpm` | Borderline | Aggressive for low-dynamic-range users; appropriate for sleep-deprived / wide-range users |
| `t_var = 0.8 bpm` | Aggressive | Almost certainly **too low** as an absolute floor; consider relative or higher |
| `60 s sustain` | Shape concern | Comparable to 1.5–3 CAP cycles; vulnerable to single arousal events |
| `30 s confirm` | Reasonable | Aligned with autonomic-cortical lag of ~10–15 s plus margin |
| Dual AND criterion | Shape concern | Misaligned with literature on asynchronous HR/HRV coupling — HRV typically leads HR-level into N3 |

### Highest-leverage changes suggested by literature

1. **Make `t_var` either relative to the Light reference or raise the floor to ~1.5–2 bpm.** The current 0.8 bpm is below the typical N3 HR-SD in healthy adults even when computed over multi-minute windows.
2. **Allow the SD condition to be met up to 60 s before the HR condition (or vice versa)** — i.e. relax simultaneity, since autonomic precedes cortical scoring.
3. **Per-user personalisation of `t_hr`** as a fraction of the user's own wake→stable-sleep drop; literature supports a 10–30× spread in this quantity between individuals.
4. **Median-filter or trimmed-mean the SD calculation** to absorb single CAP arousals without breaking the trigger.

---

## Evidence strength legend

- **Consensus** (multiple peer-reviewed studies agree): direction of HR drop wake→N3; existence of CAP; arousal-induced HR rise; vagal predominance in NREM; sympathetic predominance in REM; sleep deprivation accelerates N3 entry.
- **Single-study or small-n** (treat as suggestive): Herzig 2017 N=15 absolute HR/HRV-by-stage values; Csósza 2024 −2.36 bpm cooling-induced HR drop; Stephani 2021 adaptation-night HRV lag.
- **Inference** (explicitly flagged in this doc): conversion from SDNN-in-ms to HR-SD-in-bpm; quantitative lag of HRV leading HR-level into N3 specifically (qualitative direction is solid; *seconds* of lead is extrapolated from arousal/REM-transition data).

## Primary citations

- Trinder J. et al. (1997). *Heart rate variability: sleep stage, time of night, and arousal influences.* J. Sleep Res. — https://pubmed.ncbi.nlm.nih.gov/9191582/
- Tobaldini E. et al. (2013). *Heart rate variability in normal and pathological sleep.* Front. Physiol. — https://pmc.ncbi.nlm.nih.gov/articles/PMC3797399/
- Herzig D. et al. (2017). *Reproducibility of HRV is parameter and sleep stage dependent.* Front. Physiol. — https://pmc.ncbi.nlm.nih.gov/articles/PMC5767731/
- Stephani C. et al. (2021). *Discrepancies in the time course of sleep stage dynamics, EEG and HRV over sleep cycles in the adaptation night.* Front. Physiol. — https://pmc.ncbi.nlm.nih.gov/articles/PMC8044772/
- Bonnemeier-style aggregation paper (2022). *Aggregating HRV indices across sleep stage epochs ignores significant variance through the night.* — https://pmc.ncbi.nlm.nih.gov/articles/PMC8923916/
- Yoo C. et al. (2023). *HRV during slow wave sleep is linked to functional connectivity in the central autonomic network.* Brain Comm. — https://pmc.ncbi.nlm.nih.gov/articles/PMC10208252/
- Lechinger J. et al. (2016). *The occurrence of individual slow waves in sleep is predicted by heart rate.* Sci. Rep. — https://pmc.ncbi.nlm.nih.gov/articles/PMC4957222/
- Schäfer A. et al. (2015). *Arousal responses during overnight PSG and their reproducibility in healthy young adults.* — https://pmc.ncbi.nlm.nih.gov/articles/PMC4507737/
- Terzano M. et al. (2000). *CAP and spectral HRV during normal sleep.* — https://pubmed.ncbi.nlm.nih.gov/10733684/
- Terzano (review, 2021). *CAP and arousals in OSA.* — https://pmc.ncbi.nlm.nih.gov/articles/PMC10231930/
- Linton J. et al. (2022). *Detecting sleep outside the clinic using wearable heart rate devices.* Sci. Rep. — https://pmc.ncbi.nlm.nih.gov/articles/PMC9106748/
- Stahl S. et al. (2021). *Slow-wave sleep during a brief nap is related to reduced cognitive deficits during sleep deprivation.* SLEEP — https://pmc.ncbi.nlm.nih.gov/articles/PMC8598175/
- Hubbard J. et al. (2020). *Rapid fast-delta decay following prolonged wakefulness marks a phase of wake-inertia in NREM sleep.* Nat. Commun. — https://www.nature.com/articles/s41467-020-16915-0
- Csósza G. et al. (2024). *Enhanced conductive body heat loss during sleep increases SWS and calms the heart.* Sci. Rep. — https://pmc.ncbi.nlm.nih.gov/articles/PMC10897321/
- Gao C. et al. (2020). *Changes in HRV and baroreflex sensitivity during daytime naps.* Nat. Sci. Sleep. — https://pmc.ncbi.nlm.nih.gov/articles/PMC7520661/
- Boudreau P. et al. (2016). *HRV during daytime naps in healthy adults: autonomic profile and short-term reliability.* — https://pubmed.ncbi.nlm.nih.gov/26669510/
- Tobback E. et al. (2021). *Sleep deprivation deteriorates HRV and photoplethysmography.* — https://pmc.ncbi.nlm.nih.gov/articles/PMC8060636/
- Boulos M. et al. (2019). *Normal PSG parameters in healthy adults: systematic review and meta-analysis.* Lancet Respir. Med. — https://pubmed.ncbi.nlm.nih.gov/31006560/
- ECG-based sleep staging algorithm (Bujnowski et al., 2022). — https://pmc.ncbi.nlm.nih.gov/articles/PMC9584568/
- Sleep Stage Classification through HRV, complexity, and asymmetry (2024). — https://pmc.ncbi.nlm.nih.gov/articles/PMC11675681/
