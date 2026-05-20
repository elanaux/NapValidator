# Power Nap App — Product Document

*Last updated: May 20, 2026*

---

## 1. Current State

**Architecture (validated):**
- Continuous HR + HR SD + motion monitoring drives wake decision; wake fires before Deep sleep entry; back-by time acts as scheduling fail-safe
- HR-based stage detection validated against Apple Sleep stage labels (3 of 4 hypotheses confirmed overnight, with caveats; see Validation Findings)
- Sampling: HKWorkoutSession in `.running` state with `.mindAndBody` activity type delivers ~12 HR samples/min and 5Hz motion
- Layer A (NapAlgorithm.swift, v0.1.2, observe-only) and Layer B (SessionRecorder.swift) both shipped and integrated

**Current build state:**
- HR sample deduplication guard active (timestamp-based)
- Pause-immediately removed; sessions run unpaused
- Activity ring impact accepted as platform constraint (cannot be suppressed, will be disclosed)
- Workout entry persisted in HealthKit (allows user audit of nap-attributed ring impact); active energy and exercise time remain on rings
- Algorithm version 0.1.2 (logs motion-stall events when motion delivery throttles)
- Algorithm remains observe-only until 5-10 clean sessions confirm parameter trustworthiness

**Actively testing:**
- Parameter tuning across nap sessions (n=1 clean session as of today; targeting 5-10 for confidence)
- Deepening detection in real naps (Phase 2b/3 logic, currently observe-only)

**Parked, not blocking:**
- 5th outcome screen ("Restless/Interrupted") — waiting for 10+ sessions to reveal real patterns
- In-nap UI implementation (black-screen + wrist-raise reveal pattern designed)
- Notification alert presentation issue (delivers silently, no haptic)
- Back-by timer wiring and testing
- Second-person testing logistics

**Open architectural questions:**
- Whether Light reference SD diagnostic threshold (1-3 bpm healthy range) is reliable across users
- Whether the algorithm parameters tuned to current-user physiology generalize
- Whether motion-stall events recur now that pause-immediately is removed

**Strategic posture:**
- Direct competitive comparison: PowNap (solo dev, minimal footprint, narrower product promise — HR-onset wake vs our Light→Deep deepening detection). Existence proof that HKWorkoutSession + disclosure pattern survives App Review.
- Not competing with: passive Apple Sleep data consumers (Pillow, AutoSleep, NapBot) — those apps cannot deliver real-time wake-at-moment behavior because Apple does not produce stage labels for naps.

---

## 2. Product Concept & Positioning

> **Note:** This section reflects current working thinking and has not been deeply pressure-tested. A dedicated positioning work session is needed before locking naming, onboarding, pricing, or marketing copy. Inputs to that session should include: hands-on use of PowNap and other competitive apps, fresh-eyes critique of the current framing, and external research on knowledge-worker nap behavior. Do not treat the below as settled.

### Promise

We don't time your nap. We read your body and wake you exactly when it tells us to.

### Positioning

Productivity tool, not wellness app. Competitive set is coffee and energy drinks, not Calm or Headspace. Visual and copy register: dark UI, scientific framing, no meditation/breathing/calm language.

### Target user (working hypothesis)

Knowledge worker with afternoon meetings, flexible mid-day schedule, owns an Apple Watch. Values productivity output over wellness aesthetics. Currently relies on coffee or naps timed by phone alarm; both approaches produce inconsistent results.

### Strategic framing

The product wins on wake decision quality, not on category presence. Apple's first-party Sleep app handles overnight tracking; passive consumer apps (Pillow, AutoSleep, NapBot) handle post-hoc analysis. The unoccupied space is real-time wake-at-optimal-moment for naps — a promise no current incumbent delivers.

---

## 3. System Architecture

### Terminology note

This system measures HR sample standard deviation (HR SD) — the spread of HR values across a rolling window. This is distinct from true Heart Rate Variability (HRV), which measures beat-to-beat interval timing and requires HKHeartbeatSeries access (unavailable to third-party workout sessions, see May 14 finding). When this document refers to variability, it means HR SD unless explicitly stated otherwise.

### High-level model

Continuous HR + HR SD + motion monitoring drives a wake decision. Wake fires when Light sleep signals begin deepening toward Deep — before Deep sleep entry. A user-set back-by time acts as scheduling fail-safe.

### Sampling

- **Mechanism:** HKWorkoutSession in `.running` state with `.mindAndBody` activity type
- **HR delivery:** ~12 samples/min via HKLiveWorkoutBuilder
- **Motion delivery:** 5Hz via CMDeviceMotion
- **Wrist orientation:** Derived from gravity vector
- **Activity ring impact:** Unavoidable; disclosed in onboarding and App Store description

### Stage taxonomy

| User-facing label | Internal label | Meaning |
|---|---|---|
| Drifting | N1 | Counts as sleep |
| Light | N2 | The productive zone |
| Deep | N3 | The zone to avoid |

Internal labels (N1/N2/N3) are scientific reference only, never shown to users.

### Sleep onset and duration

- **Sleep Onset** = time from "Start nap" → entering Drifting
- **Nap Duration** = time in Drifting + time in Light
- **Session length** = Sleep Onset + Nap Duration (not displayed as primary stat)

### Algorithm structure (Layer A)

Three-phase state machine running in observe-only mode.

**Algorithm inputs:**
- HR samples (timestamps + BPM) — used to compute both rolling HR mean and rolling HR SD
- Motion samples (magnitude) — used for Phase 1 onset trigger only; Phase 2b/3 are HR-only

Phase 2b/3 are HR-only by design. Motion stalls after Phase 1 (a known platform behavior under stillness) do not affect deepening or confirmation logic.

**Phase 1: Settling**
- Captures awake reference HR (median of first 180s)
- Onset triggers when rolling 90s HR ≥ 2 bpm below awake reference AND motion RMS < 0.005 g, sustained 90s
- Transitions to Phase 2a

**Phase 2a: Light reference capture**
- 180s window after onset
- Captures Light reference HR and Light reference SD
- **Light reference HR is the algorithmic pivot** — Phase 2b decisions are anchored to this value
- **Light reference SD is the quality check** — used diagnostically to assess whether the capture window landed in stable Light sleep (expected range 1-3 bpm)

**Capture quality and contamination:**

A contaminated Light reference (SD outside the 1-3 bpm range) anchors Phase 2b's trigger to a non-stable physiological state:
- SD < 0.5 bpm → user was already deepening during capture → Light reference HR is artificially low → Phase 2b trigger needs HR to drop further than physiologically realistic → trigger may never fire even when user enters Deep
- SD > 3 bpm → user wasn't stable yet → Light reference HR is artificially high → Phase 2b trigger fires too easily → false wake before user reaches productive Light depth

Current handling: SD remains purely diagnostic; contaminated sessions are allowed to proceed and their outcomes surface in post-session wake ratings.

**Phase 2b: Deepening monitoring**
- Rolling 60s HR ≤ Light reference HR - 5 bpm AND rolling 60s HR SD ≤ 0.8 bpm
- Pattern must sustain 60s
- Transitions to Phase 3

**Phase 3: Confirming**
- Same deepening condition must persist 30s
- Confirms → fires wake decision
- Pattern reverses → returns to Phase 2b

### Session termination

A nap session ends via one of four mechanisms only. The algorithm does not have an explicit awake-state — there is no Phase 4 that detects user wake mid-session and ends the nap accordingly.

1. **Algorithm fires wake decision.** Phase 3 confirms deepening; the system triggers wake.
2. **Back-by timer fires.** User's set back-by time reached before deepening was detected.
3. **User taps Stop.** Manual termination via the wrist-raise minimal status view.
4. **User closes the app.** Treated equivalently to manual Stop; session ends with end cause logged accordingly.

These four mechanisms cover all observed user behaviors: woken by the system, capped by the schedule, woke up and ended manually, or woke up and closed the app without explicit interaction.

### Threshold design: relative HR, absolute SD

Phase 2b's trigger uses two thresholds with different anchoring:
- **HR threshold (t_hr = 5 bpm) is relative** — measured against Light reference HR captured per-session. Self-correcting to user physiology.
- **SD threshold (t_var = 0.8 bpm) is absolute** — a fixed value, not anchored to Light reference SD.

The asymmetry is intentional. Deep sleep produces low absolute HR SD across users (a physiological constant), not low SD relative to that user's Light baseline. A relative SD threshold would produce unstable triggers for users with low Light baseline variability and would be vulnerable to contamination of the SD reference. Light reference SD's role is diagnostic (quality check on capture), not algorithmic (trigger input).

### Data recording (Layer B)

Captures per session:
- HR samples (timestamps + BPM)
- Motion samples (CMDeviceMotion at 5Hz)
- Wrist orientation changes
- Screen wake/sleep events
- Session boundaries with end cause
- Battery levels at start and end
- **Workout state transitions:** HKWorkoutSessionState changes (notStarted → running → paused → ended). Instrumentation to verify session behaves as designed and detect platform-level anomalies.
- **Experiment audit:** Structured block per session capturing architecture invariants — `pausedImmediately` (should be false), `activeEnergyBurnedSampleCount`, `activeEnergyBurnedTotalKcal`, `appleExerciseTimeSampleCount`, `appleExerciseTimeTotalMinutes`. Ongoing validation that the architecture behaves as designed.
- Algorithm decisions (phase transitions, motion-stall events)
- Immediate wake rating (Sharp/Fine/Groggy/Worse)
- 3-hour follow-up rating

Storage: One JSON per session, partial flushes every 30 seconds. Filename pattern: `YYYY-MM-DD_<8char>.json`.

### Parameters (v0.1.2, placeholders, observe-only)

| Parameter | Value | Purpose |
|---|---|---|
| awake_reference_window_s | 180 | Phase 1 baseline window |
| settling_to_asleep_hr_drop | 2 | HR drop threshold for onset |
| settling_to_asleep_sustain_s | 90 | Onset sustain duration |
| motion_threshold_rms | 0.005 | Motion ceiling for onset |
| light_reference_window_s | 180 | Phase 2a capture window |
| t_hr | 5 | HR drop threshold for deepening (relative to Light reference HR) |
| t_var | 0.8 | HR SD threshold for deepening (absolute) |
| d_sustain_s | 60 | Phase 2b → Phase 3 trigger duration |
| d_confirm_s | 30 | Phase 3 verification window |

All parameters are placeholders based on n=1 data (May 15). Will be tuned as sessions accumulate. Algorithm flips out of observe-only mode when parameters are trusted across 5-10 sessions.

### Open architectural questions

1. **Should Light reference SD function as a validity gate?**
   Currently SD is diagnostic only. Two implementation options if we move to active gating:
   - Pre-capture stability gate: check rolling SD before starting Phase 2a's 180s window; wait for SD in 1-3 range before locking reference
   - Capture validity check with retry: run Phase 2a as designed; if SD lands outside 1-3, restart the window (bounded retries with fall-through to back-by)
   Decision deferred until 5-10 real sessions reveal how often contamination occurs in practice.

2. **Can d_confirm_s be reduced toward 0?**
   The 30s confirm exists to prevent false positives from transient HR dips. If Phase 3 rarely reverses in real-session logs, the confirmation window is pure delay pushing the user 30s deeper into the transition zone. Tune from observe-only data: if Phase 2b → Phase 3 → reversed back is rare, reduce d_confirm_s; if common, keep current value.

---

## 4. Platform Constraints

The product runs on watchOS, which imposes real constraints on what third-party apps can do. This section documents the constraints we operate under and the design decisions we've made in response.

### Activity ring impact (load-bearing constraint)

**What we cannot do:** Prevent nap sessions from registering on the user's Activity rings.

**Why:** Active high-resolution HR sampling on Apple Watch requires HKWorkoutSession. HKWorkoutSession in `.running` state generates `activeEnergyBurned` and `appleExerciseTime` samples that are owned by the system (`com.apple.health.*`), not by our app, even when our app initiated the workout. These samples count toward Move and Exercise rings.

We have empirically confirmed:
- Sample generation cannot be suppressed during the active session
- Post-session deletion of `activeEnergyBurned` samples does not cause ring totals to recompute downward
- `appleExerciseTime` cannot be written or deleted by third-party apps at all (Apple platform restriction)
- Activity type (`.mindAndBody` vs `.other`) does not change this behavior
- Pause-immediately appears to suppress ring credit but breaks HR sample delivery 12-17x (see "Approaches we tested and rejected" below)
- No alternative public API delivers ~12 samples/min HR without HKWorkoutSession (HKAnchoredObjectQuery, HKObserverQuery, WKExtendedRuntimeSession all gated by the same system-writer cadence of 1 sample / 3-7 min at rest)

**What we ship instead:** Explicit disclosure of ring impact in App Store description and in-app onboarding. Workout entry is left in HealthKit (rather than auto-deleted) so users can audit and reconcile their actual numbers if they choose. This pattern is established by PowNap and accepts Apple App Review.

### Screen-on during active sessions

**What we cannot do:** Turn the watch screen off during an active HKWorkoutSession.

**Why:** No public watchOS API permits screen-off while a workout session is active. The screen-on lock is fundamental to the workout session privilege model and applies regardless of activity type, session state, or any other configurable property. Every shipping third-party sleep app hits this wall. Apple's own Sleep app uses a private entitlement unavailable to third parties.

**What we ship instead:** Minimal black-screen UI when wrist is down (OLED black = pixels off, minimum glow). Wrist raise reveals a minimal status view (Active indicator, elapsed time, Stop button). No live biometric data displayed mid-nap. Theater Mode can be additionally recommended in onboarding for maximum dimness.

### Workout-in-progress chrome (green pill)

**What we cannot do:** Suppress the system "workout in progress" pill that appears at the top of the watch face.

**Why:** This is system chrome owned by watchOS, not part of our app's UI surface.

**What we ship instead:** Nothing. The pill is present throughout any active session. Disclosed if needed in onboarding.

### Motion delivery throttling (unverified)

Original hypothesis was that watchOS throttles CMDeviceMotion delivery when the watch is still + screen off, independent of any pause behavior. This hypothesis predated our discovery that pause-immediately was the actual cause of motion suppression in earlier sessions. Whether stillness-throttling exists as an independent platform behavior in unpaused sessions has not yet been tested in real nap conditions (desk sessions yesterday were short and active, not lying still in a dark room).

**What we ship:** `phase1_motion_unavailable` logging in the algorithm decision trail (v0.1.2). If motion stalls occur in real naps, they will appear in the JSON as transitions in and out of unavailability. Architectural impact is contained because Phase 2b/3 are HR-only by design.

### HR sample delivery quirk

HKLiveWorkoutBuilder's `didCollectDataOf` callback fires on the builder's internal recompute cadence, not strictly when new HR samples arrive. The callback's value comes from `workoutBuilder.statistics(for:).mostRecentQuantity()`, which returns the latest sample available — potentially the same value repeatedly if no new sample has arrived.

**What we ship:** Timestamp-based deduplication guard in SessionRecorder (May 19) — incoming samples with timestamps matching the most recently written sample are discarded.

### Apple Sleep tracking limitations

Apple does not produce sleep stage labels for naps. Daytime sessions get classified as `AsleepUnspecified` only. Overnight Sleep Mode produces rich stage data (Core / Deep / REM / Awake) but daytime nap detection produces sleep/wake binary at best.

**Implication:** Our nap algorithm cannot be validated against Apple stage labels session-by-session. Overnight comparison data serves as the validation reference for HR-pattern → stage mappings; nap-specific algorithm tuning depends on internal consistency and user wake ratings.

### heartbeatSeries unavailability

HKHeartbeatSeriesQuery does not fire during third-party workout sessions, confirmed empirically on May 14 across multiple test sessions. True HRV (beat-to-beat interval timing) from this source is not available to our app. HR SD computed from the HR sample stream is the variability metric we have access to.

### Notification alert presentation

Long-interval (3hr) local notifications scheduled from watchOS deliver silently to Notification Center without haptic alert or banner. The scheduling and delivery mechanism works end-to-end (60-second test fires correctly with alert); the presentation behavior fails for long intervals. Known issue, presentation diagnosis deferred until other priorities clear.

### Approaches we tested and rejected

**Pause-immediately for ring suppression.** Some online resources recommend pausing HKWorkoutSession immediately after `beginCollection()` to suppress activity ring credit. We tested this on May 17 and ran it as production default through May 19. Findings:

- Pause-immediately did appear to suppress activity ring credit
- But it reduced HR sample delivery rate by 12-17x (from ~12/min to ~1 unique sample/min)
- The duplication bug in SessionRecorder masked this — total sample count looked normal because the recorder wrote the same cached value repeatedly
- The motion-throttling we attributed to Sleep Mode was actually caused by pause-immediately
- Once removed, HR sampling and motion delivery both returned to expected rates

**Do not retry pause-immediately as a ring-suppression mechanism.** It does not work as advertised. The cost (sample delivery loss) exceeds the benefit (ring suppression).

---

## 5. Locked Product & Architectural Decisions

This section documents decisions that are settled. Each entry includes reasoning where it isn't obvious from the decision itself or where the context meaningfully informs future revisits.

### 5a. Product decisions (user-facing behaviors)

| Decision | Reasoning |
|---|---|
| "Back by" terminology, not "alarm" or "timer" | Productivity framing; signals intentionality rather than safety net |
| Auto-log nap to in-app history (no "Log nap" button) | Reduce friction; user just woke up, no admin needed. Refers to writing to in-app stats, not to HealthKit workout entry (that's a separate decision, see 5b). |
| "I'm awake" button replaces "End nap" | Reframes user as confirming the system's read, not overriding it |
| Arc closes at back by time, not fixed duration | Honest visual representation of the user's actual session |
| No "extend" option during nap | App is the authority on wake timing; extension undermines core value prop |
| Drifting counts as sleep | Scientific accuracy; rewards brief naps; aligns with "any nap is productive" framing |

### 5b. Architectural decisions

| Decision | Reasoning |
|---|---|
| HR-only stage detection architecture | Beat-to-beat HRV unavailable to third-party workout sessions (May 14 finding). HR + HR SD validated as sufficient signal against Apple stage labels overnight (3 of 4 hypotheses confirmed, with caveats — see Validation Findings). |
| Algorithm vs Recorder separation | Two parallel concerns kept structurally separate. Algorithm reads HR + motion, makes one decision (when to fire wake). Recorder captures full session data for analysis. Conflating creates fragility. |
| Activity ring impact accepted, disclosed openly | See Platform Constraints for full detail. No public API delivers required HR sampling rate without ring impact. PowNap precedent demonstrates HKWorkoutSession + disclosure survives App Review. |
| Pause-immediately rejected as ring-suppression mechanism | Empirically reduces HR delivery 12-17x while only partially suppressing ring credit. See Platform Constraints for full detail. |

**Workout entry persists in HealthKit (not auto-deleted at session end).**

Active energy and exercise time credits are unavoidable platform behavior — we've confirmed they cannot be deleted, written by us, or suppressed post-session. Given that ring impact is unavoidable and disclosed honestly, hiding the workout entry while not hiding the ring credits would be mixed-signal half-cleanup. Leaving the workout entry visible reinforces the honest-disclosure posture and gives technically-inclined users a way to audit and reconcile their actual numbers if they choose. Reversibility argument: if user feedback shows people want a cleaner Fitness app, deletion can be added later; reversing the other direction (un-deleting workouts users have come to expect) is harder.

---

## 6. User Experience

### 6a. Home Screen

**Purpose:** Action-oriented entry point. User opens the app to start a nap. Everything else is secondary.

**Elements:**
- Header: greeting + date/time + profile icon
- Compact "Back by" indicator with tap-to-edit time chips (default time set during onboarding)
- Primary "Start nap" button
- Four stat blocks (future-clickable into mini-dashboards):
  - Last nap
  - Avg sleep onset
  - Hours gained
  - Nap streak

**Notes:**
- The "Hours gained" stat block displays a placeholder value (e.g., "—") until methodology is defined. See Open Questions.
- No live biometric data on Home — the home screen is action-oriented, not advisory.
- The Optimal nap window block from earlier designs has been cut. A simpler circadian-anchored afternoon notification will eventually serve the "should you nap today?" prompt at the system level rather than in-app. See Open Questions.

### 6b. Sleeping Screen

**Purpose:** Minimal interface during the nap. User is asleep, not interacting.

**Behavior:**
- Pure black background when wrist is down (OLED pixels off, minimum glow)
- Wrist raise reveals minimal status view:
  - "Active" indicator
  - Elapsed session time
  - Stop button (subdued color, clearly tappable)
- Returns to black when wrist drops
- No live biometric data displayed at any point during the session
- No "extend" option — the app is the authority on wake timing
- App-close treated as "I'm awake" signal for record keeping

**Reasoning:**
Live biometric data mid-nap would (a) work against relaxation, (b) provide no actionable user value, (c) position the product closer to wellness apps than to its productivity-tool framing. Trust in the system is built through wake-moment outcomes, not through mid-session data display.

**Platform constraint reminder:**
The system "workout in progress" green pill cannot be suppressed and will be present at the top of the watch face throughout any active session. Theater Mode can be recommended in onboarding for maximum dimness.

### 6c. Wake Moment

**Purpose:** Communicate what just happened — the system's read of the nap, the user's state, what they got out of it.

**Four outcome variants, each with its own tonal identity:**

| # | Name | Color | Trigger | Headline | Subtitle |
|---|---|---|---|---|---|
| 1 | Productivity restored | Vivid green (#6b9e7a) | Deepening detected, wake fired at optimal moment | "Productivity restored." | "Your body told us when to wake you" |
| 2 | Productive nap, with room to spare | Teal (#5ea0a0) | Reached Light, back-by fired before deepening | "Productive nap, with room to spare." | "Your back by time capped you before degradation hit" |
| 3 | Ran out of runway | Amber (#e88c5a) | Only Drifting reached, back-by fired | "Ran out of runway." | "You took longer than usual to settle in" |
| 4 | Didn't quite drift off | Gray (#8b8b9e) | No sleep signal detected | "Didn't quite drift off." | "No sleep detected this session" |

**Structural pattern across all four variants:**
- Header: title + accent subtitle + profile icon
- Stat row: Nap Duration / Sleep Onset / Exit Stage
- "Your Nap" bar — segmented timeline of the session (Drifting / Light / Deep segments visualized)
- Explanation copy block — variant-specific
- "View your stats ↗" action button (auto-logging is silent; no manual log action required)

**Note on structural sameness:** All four variants share the same structural pattern; color and copy do the differentiation work. Adding visual weight to the "good outcome" screens (1-2) vs "less good" screens (3-4) is a future design question, deferred until we have more user feedback and validation data.

**Internal labels for stats history:**
- Outcome 1 → *Optimal nap*
- Outcome 2 → *Runway · Light*
- Outcome 3 → *Runway · Drifting*
- Outcome 4 → *No sleep*

**5th outcome screen (parked):**
"Restless / Interrupted" — for messy sessions where the user stirs multiple times, taps Stop mid-nap, or has fragmented sleep patterns the four-outcome model doesn't accommodate. Deferred until 10+ real sessions reveal what messy patterns actually look like. Current data capture is sufficient to detect these patterns when we're ready to design the screen.

---

## 7. Design System

- **Background:** dark (#0a0a12)
- **Brand color:** purple (#7b68ee), used for Light sleep
- **Outcome colors:**
  - Vivid green (#6b9e7a) — Productivity restored
  - Teal (#5ea0a0) — Productive nap, with room to spare
  - Amber (#e88c5a) — Ran out of runway
  - Gray (#8b8b9e) — Didn't quite drift off
- **Stage colors:** Drifting (#3d3860), Light (#7b68ee), Deep (gray placeholder; revisit when more data available)
- **Sleep Onset visual:** diagonal stripe texture, color tinted by outcome context
- **Border treatment:** 0.5px throughout
- **Bar pattern:** segmented horizontal bars for "Your Nap" timeline
- **Labeling approach:** "label what fits" — larger segments labeled inline, smaller segments speak through color
- **Timestamps:** gray reference labels, no inline timestamps below "Your Nap" bar (information lives in stat row + bar proportions)

---

## 8. Validation Findings

### 8a. Validated

| Claim | Evidence |
|---|---|
| HKWorkoutSession in `.running` state delivers ~12 HR samples/min | May 13 spike test, May 15 nap, May 19 desk test all confirmed ~12 samples/min |
| Motion delivers at 5Hz via CMDeviceMotion in unpaused sessions | May 15 nap, May 19 desk test |
| heartbeatSeries does not fire during third-party workout sessions | May 14 finding, confirmed across multiple sessions |
| Apple does not produce sleep stage labels for naps | May 18 finding, AsleepUnspecified only for daytime sessions |
| Pause-immediately reduces HR sample delivery 12-17x | May 19 architectural diagnosis, comparing May 15 (running) vs May 17-19 (paused) |
| Activity ring impact cannot be suppressed via deletion | May 19 empirical test confirmed energy samples are system-owned; appleExerciseTime cannot be written/deleted by third parties |
| Layer A state machine executes correctly end-to-end | May 19 desk test fired phase transitions as designed |

### 8b. Partially validated (needs re-validation with clean data)

| Claim | Status |
|---|---|
| HR + HR SD carry sufficient signal to distinguish sleep stages | **Indicative only.** Overnight parallel-capture vs Apple Sleep stage labels (May 17-18) showed Deep, REM, and Core HR patterns directionally matching predicted physiology. However, the data was subject to the HR duplication bug — actual unique sample density was ~1/min, not the ~12/min the algorithm requires. Re-validation needed with clean data. |

### 8c. Not yet validated / open questions

| Claim or behavior | What we'd need to validate |
|---|---|
| HR-only stage detection architecture is viable at production sampling resolution | Re-run of overnight parallel-capture with clean post-fix data |
| Onset detection identifies real sleep onset | Real nap session with algorithm decisions logged. Currently n=0 (May 15 nap predates Layer A; desk tests don't include actual sleep) |
| Deepening detection (Phase 2b/3) fires before Deep entry | Real nap sessions where user reaches Deep, with algorithm decisions logged in observe-only mode |
| Light reference SD diagnostic threshold (1-3 bpm) is reliable across users | Multi-session data showing SD distribution under known-good captures |
| Parameter values (t_hr=5, t_var=0.8, d_sustain=60, d_confirm=30) are appropriate | Tuning across 5-10 sessions; d_confirm flagged for likely reduction |
| Algorithm parameters tuned to current-user physiology generalize | n=1 user; needs second-person testing |
| Algorithm produces "good wake" outcomes by user rating | Wake rating (Sharp/Fine/Groggy/Worse) correlation with algorithm decisions across sessions |
| Motion delivery is reliable in unpaused real nap conditions | Yesterday's desk tests were short and active; not validated for lying-still nap scenarios |
| Four outcome states map cleanly to real session patterns | Need 10+ sessions to see if 5th "Restless/Interrupted" pattern emerges |
| Back-by timer fires correctly when degradation not detected | Built but never wired or tested end-to-end |
| Battery cost of full nap session is acceptable | Rough numbers exist; not systematically measured |
| Algorithm works during user motion (transit, etc.) or only stationary | Untested; current testing all stationary |
| Light reference HR captured 180s after onset is in stable Light | Plausible but unverified; depends on whether onset detection consistently lands at start of stable Light state |

---

## 9. Open Questions / Parked Items

### Product design

- Positioning deep-dive session (pressure-test promise framing AND target user definition; needs dedicated session)
- Wake experience itself (haptic patterns, audio, intensity, escalation)
- Onboarding flow (depends on persona and naming)
- App name
- Stats dashboard (what "View your stats" leads to; four home blocks become clickable mini-dashboards)
- Apple Watch experience (watch face during nap, haptic delivery, glanceable wake summary)
- Settings screen (back by defaults, notification preferences, device pairing, feedback controls)
- 5th outcome screen ("Restless/Interrupted") — design after 10+ sessions reveal patterns
- In-nap UI implementation (black-screen + wrist-raise reveal pattern designed but not built)
- Wake screen structural differentiation (good outcomes 1-2 currently look structurally identical to outcomes 3-4)
- Deep stage color (currently gray placeholder)
- Side-by-side PDF deliverable (once v1 screens are all designed)
- Generic afternoon notification spec (frequency, copy, dismissal logic; replaces the killed biometric nap coach concept)
- Investigate N1 (creativity) and N2 (insight consolidation) cognitive benefit research — implications for product positioning and potentially additional outcome states (e.g., a "creative insight" wake outcome from N1 vs "consolidation" wake outcome from deeper N2)

### Algorithm / data

- Light reference SD as validity gate (decision between pre-capture stability gate vs capture-with-retry vs leaving diagnostic-only)
- d_confirm_s reducing toward 0 (tune from real-session Phase 3 reversal data)
- d_confirm_s reduction is coupled with false-positive rate. Reducing d_confirm_s decreases algorithm latency (good for sleep-debted users) but increases false positives from transient HR dips (bad). These are not independent tuning parameters — they are a single optimization with conflicting objectives that need joint consideration.
- N3 onset acceleration in severely sleep-deprived users: extreme sleep debt can accelerate N3 onset below our minimum algorithm latency (~5.5 min from onset detection to wake decision). Affects edge-case users (severely sleep-deprived shift workers, etc.), not typical target users. Revisit if user feedback shows this population uses the product.
- Literature review on HR and HR SD characteristics across NREM stages (specifically Light → Deep transition). Current thresholds (t_hr=5 bpm, t_var=0.8 bpm) are placeholders derived from n=1 nap data; published literature on stage-transition HR dynamics would inform whether these are conservative, aggressive, or appropriate. Suitable as a Code research task.
- Arousal event handling: research indicates 3-4 brief arousals per nap is common (HR spikes without conscious wake). Phase 2b currently resets when conditions reverse, meaning frequent arousals could prevent deepening detection from ever firing. Open question whether this is correct behavior (arousals indicate user proximity to wake, no fire needed) or problematic (arousals occur within continuous N2 without indicating wake proximity).
- HR vs HR SD temporal dynamics during Light → Deep transition: Phase 2b requires both conditions in lockstep (HR drop AND SD drop). Research gap on whether these fall asynchronously during real transitions; if SD stabilizes first followed by HR drop (or vice versa), our AND requirement could miss the actual transition window.
- Post-nap follow-up question design — unanchored phrasing that doesn't prime users
- Follow-up timing methodology — what's the right interval? Currently arbitrary, needs grounding
- Focus Recovery bar revisitable after N sessions of unanchored data showing meaningful pattern
- Re-validation of overnight stage detection with clean (post-fix) data
- Validation of motion delivery reliability in real (lying-still) nap conditions
- "Hours gained" methodology definition

### Engineering

- Back-by timer wiring and testing
- Workout entry deletion code removal (no longer needed; we leave workout entries in)
- Notification alert presentation fix (currently silent delivery for long intervals)
- Old format JSON file migration cleanup
- Pilot feedback mechanism design

### Operations

- Git basics literacy session (foundational for Code work generally)
- Remove stale `.git/` from `~/Desktop/nap-app/` outer directory next time at terminal
- Second-person testing logistics
- PowNap hands-on evaluation (install, use for a week)

### Strategic / business

- Pricing & business model strategy session (60-90 min, fresh head)
- WWDC Code project (June 6-7, weekend before WWDC)
- Cross-platform expansion (Wear OS, Oura, WHOOP integrations) — long-term

---

## 10. Research Foundation

The science underlying the product approach. Claims here are calibrated to what current research actually supports — not to what would be most flattering to the product story.

### Sleep architecture and the productive nap window

- Avoiding N3 (Deep) sleep is the well-supported goal for nap timing. Waking from N3 produces sleep inertia lasting 15-30+ minutes.
- N3 onset typically occurs approximately 30 minutes after sleep onset, though timing varies with sleep pressure and individual factors.
- N2 sleep supports several cognitive benefits, including memory consolidation and recent research linking N2 specifically to "insight" moments (problem-solving aha experiences).
- N1 sleep has been associated with creativity benefits in recent research.
- N2 has internal physiological heterogeneity — signals begin shifting toward N3 characteristics before formal stage transition. This pre-N3 deepening window is what our Phase 2b/3 algorithm targets.

### Homeostatic sleep regulation

- Sleep debt increases homeostatic pressure for Deep sleep, accelerating onset and increasing N3 proportion in subsequent sleep periods.
- This means the same nap on different days (after a normal night vs. a short night) can produce different sleep architectures. The algorithm must adapt to this within-session by anchoring to that session's captured Light reference rather than to absolute thresholds.

### Wearable sleep detection accuracy

- Binary sleep/wake detection on consumer wearables is well-validated; specific accuracy figures vary by device and study generation.
- Multi-stage sleep classification (N1/N2/N3/REM) is substantially lower accuracy than binary detection.
- Apple Watch Sleep Tracking specifically produces stage labels only for overnight Sleep Mode contexts, not for nap-duration sessions.

### Circadian timing

- The post-lunch alertness dip is a circadian phenomenon (driven by a circasemidian 12-hour rhythm component), not a meal-driven effect. It occurs even when individuals skip lunch entirely.
- Typical timing is 2-4 PM for most individuals.
- The dip is not universal — research shows it affects many but not all people, with individual variation tied to chronotype, age, and other factors.
- This is the window when most users will benefit from a nap, and it informs the eventual afternoon notification.

### Post-nap benefit duration

Research on power nap cognitive benefits (Tietzel & Lack 2001, Brooks & Lack 2006, and subsequent reviews) finds that benefits typically emerge within minutes post-wake and persist for approximately 1.5-2.5 hours. The specific duration varies by nap length, prior sleep restriction, and outcome measure. The bulk of this research has been conducted on sleep-restricted participants; effects on well-rested individuals are less well-characterized.

Note: This claim is research-supported but is not surfaced as a UI element (e.g., a "peak window ends at X" bar) because doing so anchors user expectations in ways that contaminate our own post-nap validation data. The research informs our internal thinking; the user-facing product does not make this specific prediction per-nap.
