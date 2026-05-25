# Competitive research: do third-party sleep/nap apps using HKWorkoutSession generate ring-pollution complaints?

Scope: open-web search for evidence that users notice or complain when watchOS sleep/nap apps create exercise-minute credit, move-calorie credit, or workout entries via HKWorkoutSession. Includes Reddit, App Store reviews, Apple Developer Forums, app support pages, and indie-dev writing.

---

## 1. Executive summary

- **End-user complaints about ring/calorie pollution from sleep apps are surprisingly rare in the public corpus.** Across Reddit, App Store reviews, and Apple Community threads, I could not find a single high-signal thread of users complaining "App X gave me fake exercise minutes / fake calories / a phantom workout entry while I slept." Negative reviews of AutoSleep, Pillow, NapBot, SleepWatch, and Sleep++ overwhelmingly cluster on (a) detection accuracy (false sleep, missed sleep, inflated duration) and (b) subscription pricing. Ring-impact is essentially absent as a review theme.
- **The dominant market leader (AutoSleep) avoids the problem entirely by NOT using HKWorkoutSession.** AutoSleep's own docs describe it as relying on passive, OS-provided background heart-rate samples plus motion — explicitly stating it works "fully automatic" with no session required. This is the most important competitive data point for the user: the highest-volume Apple-Watch sleep tracker on the App Store ships without an HKWorkoutSession, accepting whatever HR cadence the OS gives during sleep mode.
- **Apple App Review actively rejects HKWorkoutSession misuse for non-fitness HR collection.** Multiple developer-forum threads document apps being rejected for "unintended use of HKWorkoutSession" when the app's primary purpose isn't fitness — Apple's recommended alternative is `WKExtendedRuntimeSession` (Mindfulness type), though that caps at ~1 hour. This is a regulatory risk separate from end-user complaints.
- **The one app that does openly use HKWorkoutSession for nap detection — PowNap — discloses it explicitly in the App Store description** ("PowNap uses a Mind & Body workout session because watchOS requires continuous heart-rate monitoring. Activity Rings may be affected."). It has very few reviews, but none of the visible ones complain about ring pollution. This is one data point suggesting honest disclosure may neutralize complaints, but the sample is tiny.
- **"Mind & Body" workout type used to be ring-neutral and no longer is.** Apple Community threads note that older watchOS versions excluded Mind & Body from the Exercise Ring; recent watchOS versions count it. So the historical workaround (use Mind & Body to dodge ring credit) no longer reliably works.

The headline takeaway for the user: **ring pollution from sleep apps is a real technical problem, an active App Review rejection vector, but NOT a meaningful end-user complaint category on the public web.** The strongest competitive evidence is that the category leader sidesteps it architecturally rather than mitigating it.

---

## 2. Findings by app

### AutoSleep (Tantsissa)

- **Source — AutoSleep FAQ**: https://autosleepapp.tantsissa.com/faq
- **Source — AutoSleep Quick Guide**: https://autosleepapp.tantsissa.com/user-guide/quick-guide
- **Behavior**: AutoSleep does not start an HKWorkoutSession during sleep. The docs describe it as automatic and dependent on passive HR sampling from the OS. Requirements listed are about enabling Heart Rate / Fitness Tracking permissions, Wrist Detection, and avoiding Low Power Mode (which "will turn off background heart measures") — all consistent with the OS's own passive HR cadence, not an app-driven session. There is no mention of activity rings, exercise minutes, or workout entries being created.
- **Reviews**: Visible App Store reviews for AutoSleep (https://apps.apple.com/us/app/autosleep-track-sleep-on-watch/id1164801111) make no mention of ring credits, workout entries, calorie pollution, or fake workouts. Complaints cluster on accuracy and subscription model.
- **Severity of complaint**: non-issue in the public corpus.
- **Developer response**: N/A — the architecture sidesteps the problem.
- **Significance**: This is the most-installed third-party Apple Watch sleep tracker in the category, and it ships without HKWorkoutSession. That is the strongest single data point in this research.

### Pillow (Neybox)

- **Source — App Store page**: https://apps.apple.com/us/app/pillow-automatic-sleep-tracker/id878691772
- **Source — feature page**: https://pillow.app/article/heart-rate-and-sleep-using-pillow
- **Behavior**: Marketing copy describes heart-rate monitoring during sleep but the app description and support docs do not disclose using HKWorkoutSession or affecting Activity Rings.
- **Reviews**: No visible negative reviews mention ring credit, workout entries, fake workouts, or calorie pollution. Complaints focus on accuracy, automatic-detection misfires, and paywall friction.
- **Severity**: non-issue in the public corpus.
- **Developer response**: N/A.

### NapBot (Sebastian Niemann / Swift with Majid)

- **Source — App Store page**: https://apps.apple.com/us/app/napbot-auto-sleep-tracker/id1476436116
- **Source — product site**: https://napbot.swiftwithmajid.com/
- **Behavior**: Product positioning emphasizes on-device ML over passive HealthKit data ("uses on-device Machine Learning to detect and understand your sleep"). No disclosure of HKWorkoutSession, Activity Ring impact, or workout entries. Heart-rate display is described as a summary built from HR zones, consistent with reading existing HealthKit samples rather than driving sampling via a workout session.
- **Reviews**: Negative reviews complain about over-eager sleep detection ("decides I'm sleeping every time I sit still or lay down, even if I'm on my phone") and inflated sleep duration. No reviews mention ring credit, exercise minutes, workout entries, or polluted Health data.
- **Severity**: non-issue in the public corpus.
- **Developer blog signal**: I could not surface a Sebastian Niemann blog post directly addressing the HKWorkoutSession-vs-passive-HR tradeoff. (Gap noted in methodology.)

### SleepWatch (Bodymatter)

- **Source — App Store page**: https://apps.apple.com/us/app/sleepwatch-top-sleep-tracker/id1138066420
- **Source — third-party review aggregator**: https://justuseapp.com/en/app/1138066420/sleep-watch-by-bodymatter/reviews
- **Behavior**: App description discloses "integrates with the Health app" but says nothing about workout sessions or Activity Ring contributions.
- **Reviews**: One review I found is interesting and partially relevant — a user complains that "Sleep Watch takes this data and then adds its own inaccurate data to Apple Health, rendering that data inaccurate." This is the closest thing I found to a "polluted my Health data" complaint, but it is about sleep records, not about workout entries or ring credit. No reviews specifically mention activity rings, exercise minutes, or fake workouts.
- **Severity**: minor annoyance about Health-data writes generally, not specifically ring pollution.
- **Developer response**: not visible in the reviews I could see.

### Sleep++ (David Smith)

- **Source — App Store page**: https://apps.apple.com/us/app/sleep/id1038440371
- **Source — Sleep++ FAQ**: https://sleepplusplus.app/faq
- **Source — developer blog**: https://www.david-smith.org/blog/2018/03/20/automatic-sleep-tracking-with-sleep-plus-plus-3-dot-0/
- **Behavior**: David Smith's automatic-sleep-tracking writeup describes Sleep++ as a consumer of existing passive HealthKit data ("the Apple Watch is always silently collecting a variety of health metrics... Sleep++ uses the Health data collected by your Apple Watch to analyze your sleep"). He does not describe using HKWorkoutSession to drive HR sampling. The Readiness Score post describes using HRV / RHR / duration but doesn't claim to drive sampling. None of his blog posts I read discuss the HKWorkoutSession-vs-passive tradeoff explicitly.
- **Reviews**: One Sleep++ 1-star review (cited in App Store search aggregators) complains that the app logged them as sleeping for 13 hours while they were actively lifting and doing yoga — this is a sleep-detection-vs-workout conflict, not ring pollution from Sleep++ creating workouts. Reviewer: "flabbergasted that this app is so inaccurate." No reviews complain about Sleep++ generating exercise minutes or fake workouts.
- **Severity**: non-issue in the public corpus for ring pollution; modest signal for sleep/workout misclassification (different problem).
- **Developer response**: N/A on this specific concern.

### Sleep Cycle

- **Source — search results**: no specific ring-pollution complaints surfaced. Sleep Cycle is largely iPhone-microphone-based with optional Apple Watch integration, so HKWorkoutSession use is less likely a primary design choice.
- **Severity**: non-issue in the public corpus.

### Pokémon Sleep

- **Source — Apple Watch integration FAQ**: https://www.pokemonsleep.net/en/devices/ios/
- **Behavior**: Pokémon Sleep does NOT run on Apple Watch and does not write workouts. It reads sleep data already in Health, via the iOS Health app. Not relevant to the HKWorkoutSession concern.
- **Severity**: N/A.

### Power Nap App (VisualHype) and Power Nap Tracker

- **Source — search results**: short-duration nap timers; no public discussion of HKWorkoutSession or ring impact. These older nap timers appear to be iPhone-side.
- **Severity**: N/A.

### PowNap (the one app that *does* openly use HKWorkoutSession on the watch)

- **Source — App Store page**: https://apps.apple.com/us/app/pownap/id6743547737
- **Behavior — explicit disclosure (quoted from App Store description)**: *"PowNap uses a Mind & Body workout session because watchOS requires continuous heart-rate monitoring. Activity Rings may be affected."* That language appears in the "Important" section of the App Store description.
- **Reviews**: Very few reviews visible. The one 5-star review surfaced ("SaphiraCat") makes no complaint about ring pollution. The app's recent updates note "improved Mind & Body workout handling, making activity tracking explicit instead of implicit" — suggesting the developer was actively iterating on this UX.
- **Severity**: no negative-review signal yet — but also a tiny review base, so absence of complaints is weak evidence.
- **Developer response**: proactive disclosure in store listing; iterating to make the side-effect "explicit instead of implicit."
- **Significance**: PowNap is the cleanest in-market example of "do the thing, disclose it openly." So far it has not produced visible blowback, but the sample is too small to draw strong conclusions.

### ShutEye / Sleepiest

- No signal found in searches. These are primarily iPhone-based; no evidence of HKWorkoutSession use or related complaints.

---

## 3. Findings by theme

### 3a. Ring-credit complaints from sleep apps

Effectively absent on the public web. I ran multiple variations (reddit site-restricted, broader Google, App Store reviews) and found zero on-point complaints in the form "sleep app X added exercise minutes / closed my ring while I was asleep / inflated my calories." The closest adjacent signals are:

- General complaints that Apple's own Workout app generates phantom workouts when left running — e.g. https://discussions.apple.com/thread/253604263 ("How to get rid of false training data") and https://discussions.apple.com/thread/253062756 ("Apple watch fake workout"). These are about Apple's stack, not third-party sleep apps.
- A user-of-a-meditation-app thread asking "Why do meditation apps count as exercise [on the ring]?" — https://discussions.apple.com/thread/8382207 — confirms that the broader category (apps that hold a workout session while you're stationary) does generate user confusion, just not specifically in the sleep vertical.
- The 9to5Mac comment thread noted in passing: "previously in older watchOS versions, 'Mind and Body' exercise type did not count toward activity/exercise rings, but with recent updates... even that type of exercise will count." This kills the historical loophole.

### 3b. "Polluted my Health data" complaints

The closest signal: a SleepWatch review complaining the app "adds its own inaccurate data to Apple Health, rendering that data inaccurate." But this is about sleep records, not workouts. The category-wide pattern is that users get upset about *bad sleep records*, not about *side-effect workout records*. The latter is essentially invisible in the corpus.

### 3c. Fake / phantom workout entries

Complaints exist in the Apple-stack corpus (forgotten workouts left running, sweat-triggered taps, etc.) but I found zero attributing the cause to a third-party sleep app. Either the apps that do this are silent about it and users don't connect the dots (plausible), or most sleep apps don't actually call `finishWorkout()` and so don't materialize a saved workout (also plausible — see Apple DTS guidance in §4).

### 3d. Transparency / disclosure norms

- **AutoSleep**: silent about workout sessions (because it doesn't use one).
- **Pillow**: silent.
- **NapBot**: silent.
- **SleepWatch**: silent.
- **Sleep++**: silent.
- **PowNap**: explicitly discloses Mind & Body workout session and "Activity Rings may be affected." Unique in this set.

The norm in the category is to NOT disclose. PowNap is the outlier. The norm is also to NOT use HKWorkoutSession.

### 3e. Developer responses

I found no developer (in App Store responses, blog posts, or forum replies) acknowledging-and-fixing ring-pollution complaints from a sleep app, because there are no such complaints. The relevant developer-side discussion is all on the Apple Developer Forums and is upstream — devs asking *how to avoid* ring contribution, before shipping.

---

## 4. Apple Developer Forum discussion

This is where the signal is strongest. Several long threads document developer pain and Apple's official position.

- **"HKWorkoutSession: don't contribute to Activity Ring"** — https://developer.apple.com/forums/thread/66186 (2016, ongoing). Developer asks how to use HKWorkoutSession for HR monitoring without contributing to the Move/Exercise rings. No Apple engineer responds. Peer-suggested workarounds include immediately pausing the session, and the speculation that Cardiogram programmatically deleted the auto-created HealthKit data. Key quote (developer): *"Starting HKWorkoutSession will always contribute to the Exercise Ring but not the Move Ring unless you exclusively write to healthkit."*
- **"How to run HKWorkoutSession on watch for extended periods"** — https://developer.apple.com/forums/thread/780220 (research app at Clemson tracking eating behavior). Apple DTS Engineer response: *"is it appropriate to not call `finishWorkout(completion:)` after stopping the workout? That way, you can still collect the data points while the workout is ongoing, and don't impact the rings because the workout data isn't saved."* This is the most useful official-Apple guidance in the corpus: **don't finalize the workout and it won't materialize as a Health-app entry**. (Note: this addresses the *workout entry* problem but it's less clear whether ring credit accrues while the session is live; the Clemson app's audience was research subjects, so user reaction wasn't relevant.)
- **"Will it be possible to get heart rate readings only by Using [Extended Runtime Sessions]"** — https://developer.apple.com/forums/thread/130287. The developer's app (2-minute mindfulness HR check) *was rejected multiple times* by App Review for "unintended use of HKWorkoutSession." Apple recommended `WKExtendedRuntimeSession` instead, and an Apple Documentation Engineer wrote out the full alternative stack (Extended Runtime + HKObserverQuery + HKSampleQuery). However the developer reported that on watchOS, HR updates stopped 15 seconds after the watch went to sleep — confirming the practical limitation: passive observer queries do not give you continuous live HR when the screen is off, you have to wait for whatever cadence the OS chooses to deliver.
- **"Requirements to use HKWorkoutSession"** — https://developer.apple.com/forums/thread/671859. Apple rejection language quoted: *"We noticed that your app uses HKWorkoutSession, but your app does not appear to include any primary features that require fitness data. The intended use of HKWorkoutSession is to record data during a workout, and it should only be used in apps that require this data as part of the app's core functionality."* Apple Frameworks Engineer recommends `WKExtendedRuntimeSession` (Mindfulness type — note the 1-hour cap). This is the rejection precedent most directly applicable to a nap app: the user's app, framed primarily as a sleep/nap tracker rather than a workout app, is at meaningful risk of this rejection if it ships HKWorkoutSession.
- **"Having a workout count toward the [green ring]"** — https://developer.apple.com/forums/thread/4975. Older (2015) thread. Confirms long-standing fact that the activity-type filter governs ring contribution; `.other` (and historically `.mindAndBody`) had different ring behavior than other types. This is the historical basis for the now-defunct Mind & Body loophole.

**Synthesis from the developer forums**: Apple's position is consistent and clear — HKWorkoutSession is for fitness apps, and using it primarily to get high-cadence HR is grounds for App Review rejection. The recommended alternatives (`WKExtendedRuntimeSession`, audio background session, passive HealthKit observer queries) all have substantial cadence/duration tradeoffs vs. a live workout session. Developers know this is a tradeoff; Apple knows developers want a back door and isn't providing one.

---

## 5. Methodology note (be honest about gaps)

What I searched:

- WebSearch queries on Reddit (`site:reddit.com`) for multiple combinations of sleep-app names + "exercise ring", "fake workout", "added workout", "polluted", "calorie", "ring credit", "exercise minutes". Most Reddit site-restricted queries returned zero results, which is itself a finding but also reflects that the search engine's Reddit coverage may be patchy.
- WebSearch on App Store for negative reviews of AutoSleep, Pillow, NapBot, SleepWatch, Sleep++, Power Nap, Pokémon Sleep, PowNap, ShutEye/Sleepiest.
- WebFetch on App Store listings to read the visible review snippets directly.
- WebFetch on the support / FAQ sites for AutoSleep, Pillow, NapBot, Sleep++, PowNap to check disclosure norms.
- WebSearch + WebFetch on Apple Developer Forums for HKWorkoutSession + sleep / mindfulness / non-fitness threads.
- WebSearch for David Smith and Sebastian Niemann developer blog posts on the topic.

Gaps and caveats:

- **App Store reviews are paginated and the WebFetch view only surfaces the top few reviews per app.** A complaint that exists on review page 47 will not appear here. The signal that "there are no ring-pollution complaints" is therefore strongest for top-rated apps where I sampled visible reviews; it is weaker for the long tail. Recommend the user do an in-Store search on iPhone for each app, sorted by Most Critical, to confirm.
- **Reddit search via web-search was thin.** Many site-restricted queries returned zero results, which is unusual. The user may want to search Reddit directly (search.reddit.com) for "AutoSleep exercise ring" etc.; my web-search-based attempts may have missed posts that exist.
- **I could not surface a specific Sebastian Niemann (NapBot) blog post on the HKWorkoutSession tradeoff.** It may exist on the swiftwithmajid.com domain but wasn't indexed under the queries I used. Worth checking that blog directly.
- **I could not confirm via primary source whether AutoSleep technically uses HKWorkoutSession.** My conclusion that it does not is inferred from (a) its support docs, which describe passive background HR sampling and OS-side requirements (Wrist Detection, no Low Power Mode), and (b) absence of any workout-entry complaints in reviews. A more rigorous test would be to install AutoSleep and check Health → Workouts after a night of sleep tracking. The user should confirm before relying on this in any product decision.
- **App-Review rejection trends can shift.** The threads I cite span 2016–2024. The user should treat "Apple rejects HKWorkoutSession for non-fitness apps" as a directional risk rather than a guaranteed outcome.
- **PowNap is so new and has so few reviews** that "no complaints visible" is near-meaningless evidence. It does prove the disclosure model is at least permitted by App Review.

What I did not search:

- Mastodon / Bluesky (the search tool doesn't index them well).
- Twitter/X (search results are no longer reliably surfaced in web search).
- Apple Developer Slack / Discord communities.
- Non-English-language reviews and forums.
- Sebastian Niemann's personal site for primary-source dev commentary.

**Confidence level on the headline findings**:

- High confidence: Apple App Review treats HKWorkoutSession-for-HR as a rejection vector, with documented Apple statements.
- High confidence: PowNap discloses ring impact in its App Store listing.
- Medium-high confidence: User-facing complaints about ring pollution from sleep apps are rare to non-existent in the public corpus.
- Medium confidence: AutoSleep does not use HKWorkoutSession (inferred from docs + absence of complaints; not verified by running the app).
- Medium confidence: The Mind & Body workout type no longer dodges ring credit (based on community report; not verified against current watchOS release notes).
