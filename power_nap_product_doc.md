# Power Nap App — Product Doc

*Last updated: May 2026*

## Concept

A biometric-powered nap optimization app that wakes users at the right moment using continuous monitoring of HR, HRV, and motion data from a wearable. The system reads the body's transition through sleep stages and triggers wake when Light sleep starts deepening toward Deep sleep — eliminating the grogginess of waking from deep sleep without relying on arbitrary timer-based wake.

**One-liner promise:** *We don't time your nap. We read your body and wake you exactly when it tells us to.*

## Positioning

- **Productivity tool, not wellness app.** Competitive set is coffee and energy drinks, not Calm or Headspace.
- **Visual and copy register:** dark UI, scientific framing, no meditation/breathing/calm language.
- **Target user:** knowledge worker with afternoon meetings, flexible mid-day schedule, owns an Apple Watch.

## Platform

- **v1:** Apple Watch + iPhone (iOS / watchOS)
- **v2+:** Wear OS (Android), Oura, WHOOP integrations — parked, not in initial scope
- Apple Watch chosen first based on installed base (~32% global smartwatch share, leader in target geographies) and HealthKit data access without partnership agreements

## System Architecture (Locked)

**Three-layer detection model:**

1. **Continuous monitoring.** HR, HRV, and motion read in real time throughout the session via HealthKit.
2. **Degradation-based wake.** System triggers wake when Light sleep signals start deepening toward Deep — the moment of N2→N3 transition. No N1→N2 timer; the user's body decides when to wake, the system just reads it.
3. **Back by time as schedule cap.** Fires only if degradation hasn't been detected by the user's set time. Protects the user's calendar, not their sleep stage.

**Sleep stage taxonomy (user-facing):**
- **Drifting** = N1 (counts as sleep)
- **Light** = N2 (the productive zone)
- **Deep** = N3 (the zone to avoid)
- *Internal labels (N1/N2/N3) are scientific reference only and never shown to users.*

**Sleep onset definition:**
- Sleep Onset = time from "Start nap" → entering Drifting (the moment sleep begins)
- Nap Duration = time in Drifting + time in Light (total time asleep)
- Session length = Sleep Onset + Nap Duration (not displayed as a primary stat)

## Outcome States (User-Facing Wake Screens)

Four locked screens, each with its own tonal identity:

### 1. Productivity restored (vivid green)
- System detected degradation and woke user at the ideal moment
- Hero outcome
- Headline: "Productivity restored."
- Subtitle: "Your body told us when to wake you"
- Internal/stats label: *Optimal nap*

### 2. Productive nap, with room to spare (teal)
- User got real Light sleep but back by fired before degradation could trigger
- Honest framing: solid outcome, but suggests room to extend back by
- Headline: "Productive nap, with room to spare."
- Subtitle: "Your back by time capped you before degradation hit"
- Internal/stats label: *Runway · Light*

### 3. Ran out of runway (amber)
- User took too long to fall asleep; back by fired with only Drifting reached
- Coaching nudge: try napping earlier or in a quieter setting
- Headline: "Ran out of runway."
- Subtitle: "You took longer than usual to settle in"
- Internal/stats label: *Runway · Drifting*

### 4. Didn't quite drift off (gray)
- No sleep signal detected throughout session
- Empathetic framing with data-collection reframe
- Headline: "Didn't quite drift off."
- Subtitle: "No sleep detected this session"
- Internal/stats label: *No sleep*

**Fifth screen (parked, not yet designed):** Early wake — auto-detected via motion/device pickup, or via "I'm awake" button tap. Different from the four above because user woke on their own before degradation.

## Locked Screens

### Home Screen
- Greeting + date/time + profile icon (consistent header pattern)
- Optimal nap window block: shows live biometrics (resting HR, HRV, readiness score)
- Compact "Back by" indicator with tap-to-edit time chips
- Primary "Start nap" button
- Four stat blocks (future-clickable into mini-dashboards):
  - Last nap
  - Avg sleep onset
  - Hours gained
  - Nap streak
- Nap coach lives in notifications only, not on home screen

### Sleeping Screen
- Minimal interface — user is asleep, not interacting
- Arc timer that closes at "Back by" time (anchored to user's session, not arbitrary maximum)
- Live biometric readouts: HR, HRV, Motion
- Pulsing stage pill showing current detected stage
- "Back by" time display with "failsafe active" indicator
- Single prominent "I'm awake" full-width button for early wake confirmation
- No "extend" option — the app is the authority on wake timing
- App-close treated as "I'm awake" signal for record keeping

### Wake Moment Screens (4 variants — see Outcome States above)
- Consistent structural pattern across all four:
  - Header (title + accent subtitle + profile icon)
  - Stat row: Nap Duration / Sleep Onset / Exit Stage
  - "Your Nap" bar (segmented timeline of the session)
  - "Focus Recovery" bar (where applicable — Productivity Restored and Runway · Light only)
  - Explanation copy block
  - "View your stats ↗" action button (auto-logging is silent)

## Design System

- **Background:** dark (#0a0a12)
- **Brand color:** purple (#7b68ee), used for Light sleep
- **Outcome colors:**
  - Vivid green (#6b9e7a) — Productivity restored
  - Teal (#5ea0a0) — Productive nap, with room to spare
  - Amber (#e88c5a) — Ran out of runway
  - Gray (#8b8b9e) — Didn't quite drift off
- **Stage colors:** Drifting (#3d3860), Light (#7b68ee), Deep (gray placeholder)
- **Sleep Onset visual:** diagonal stripe texture, color tinted by outcome context
- **Border treatment:** 0.5px throughout
- **Bar pattern:** segmented horizontal bars for both "Your Nap" and "Focus Recovery"
- **Labeling approach:** "label what fits" — larger segments labeled inline, smaller segments speak through color
- **Timestamps:** gray reference labels, no inline timestamps below "Your Nap" bar (information lives in stat row + bar proportions)

## Nap Coach Notification Logic

- **Cold start (first ~10 naps):** Generic circadian-anchored notification at start of dip window. Example: *"Your circadian dip starts around 2 PM. Many people find this an ideal nap window."*
- **Warm state (after enough data):** Personalized to user's own successful nap timing pattern. Example: *"Your most successful naps tend to be around 2:15 PM. Want to give it a try today?"*
- **Frequency:** Conservative, scaling back if dismissed
- **Calendar integration:** Parked for v2+ — explicitly out of v1 scope to avoid product expansion
- **Sleep tracker overlap:** Explicitly avoid framing notifications around overnight sleep quality. Stay disciplined about scope.

## Key Product Decisions (and Reasoning)

| Decision | Reasoning |
|---|---|
| "Back by" terminology vs. "alarm" or "timer" | Productivity framing, signals intentionality rather than safety net |
| Auto-logging every nap | Reduce friction; user just woke up, no admin needed |
| "I'm awake" button replaces "End nap" | Reframes user as confirming, not overriding the system |
| Arc closes at back by time, not fixed duration | Honest visual representation of user's actual session |
| Nap coach in notifications only | Keeps home screen action-oriented, not advisory |
| No "extend" option during nap | App is the authority; extension undermines core value prop |
| Drifting counts as sleep | Scientific accuracy; rewards even brief naps; aligns with "any nap is productive" framing |
| Multiple naps per day not encouraged | Research supports one nap in 1–3 PM window; product should guard against misuse |
| "Hours gained" methodology | Still to be defined — needs transparent, defensible scoring |

## Open Questions / Parked Items

- **Wake experience itself** (haptic patterns, audio, intensity) — not yet designed
- **Pilot feedback mechanism** — post-wake "How do you feel?" prompt for calibration during pilot
- **Persona definition** — needed before app naming and onboarding
- **App name** — TBD
- **Onboarding flow** — depends on persona and name
- **Stats dashboard** — what "View your stats" leads to; four home screen blocks become clickable mini-dashboards
- **Apple Watch experience** — watch face during nap, haptic delivery, glanceable wake summary
- **"Hours gained" methodology** — define exact calculation
- **Settings screen** — back by defaults, notification preferences, device pairing, feedback controls
- **Side-by-side PDF deliverable** — once v1 screens are all designed
- **Cross-platform expansion** — Wear OS, Oura, WHOOP integrations (long-term)

## Critical Technical Assumptions (Still To Validate)

1. Apple Watch can deliver real-time HR + HRV data via HealthKit during a nap with low enough latency to detect N2→N3 degradation before it completes
2. The degradation signal (HR continuing to drop, HRV beginning to flatten) is detectable with consumer-wearable signal quality, not just research-grade equipment
3. Sleep onset detection (awake → Drifting) is reliable enough that the Sleep Onset metric is trustworthy
4. The algorithm can run continuously without draining device battery to the point of user complaint

**These are not validated yet.** Architecture pivot may be required once real-world data is available.

## Research Foundation

- N2 (Light) sleep is the power-nap sweet spot; wake here = peak alertness, no inertia
- N3 (Deep) onset typically occurs around 20–30 min into a nap; waking here causes 15–30 min of grogginess
- Sleep debt accelerates N2→N3 transition (homeostatic rebound)
- Apple Watch HRV is ~99.3% accurate vs. medical-grade ECG (2025 study)
- Binary sleep/wake detection on wearables achieves ~87–89% accuracy; multi-stage classification is lower (~50–60%)
- Post-lunch dip is a circadian phenomenon (1–3 PM), independent of meal — universal across populations
- N2 has internal gradient (N2a → N2b) where physiology starts approaching Deep sleep before formal stage labels would shift
- Power nap cognitive benefit window typically lasts ~1.5–2.5 hours post-wake

---

## Working Notes

- This doc is a living artifact. Update locked decisions, parked items, and validation status as work progresses.
- For new Claude conversations, paste relevant sections of this doc to load context efficiently rather than re-explaining.
- Periodic review: every 2–3 working sessions, audit which "Parked" items have moved forward and which "Locked" items need revisiting based on new data.
