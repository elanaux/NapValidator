# Valentin Haberling — Developer Profile (PowNap, CalDown)

Compiled 2026-05-19. Read-only desk research. Tags: **[Verified]** = primary source (Apple App Store, his own site, direct quote on his site). **[Inferred]** = derived from indirect evidence. **[Unknown]** = searched and not found.

---

## 1. Online presence

A broad sweep across LinkedIn, X/Twitter, Mastodon (mastodon.social, iosdev.space), Bluesky, GitHub, Indie Hackers, Product Hunt, Hacker News (Algolia), Reddit, Medium, Substack, Dev.to, Xing, Instagram, Threads, and German tech-press forums (heise, macwelt, iphone-ticker) returned **no findable personal account** under the name "Valentin Haberling" tied to PowNap/CalDown.

- **LinkedIn**: No profile matching "Valentin Haberling" surfaces in `site:linkedin.com` searches; the surname returns ~20 other Haberlings (mostly German), but no Valentin. **[Unknown]** (https://www.linkedin.com/pub/dir/+/Haberling)
- **X / Twitter**: No account at `@valentinhaberling`, `@vhaberling`, `@valentin_h`, `@pownap`, or `@caldown` surfaces. `twitter.com/haberling` exists but no evidence ties it to him. **[Unknown]**
- **Mastodon (incl. iosdev.space, indieapps.space)**: No posts indexed mentioning PowNap, CalDown, or Haberling. **[Unknown]**
- **Bluesky**: No matches via `site:bsky.app`. **[Unknown]**
- **GitHub**: `vhaberling`, `valentinhaberling` do not exist. The previously identified `valentinap` is confirmed-not-him (prior research). No findable repo or profile. **[Unknown]**
- **Personal website**: `valentinhaberling.com` and `haberling.dev` both return connection refused (no DNS / not registered). **[Verified — no site at obvious vanity domains]**
- **Indie Hackers**: No user page, product page, or post. **[Unknown]**
- **Product Hunt**: `producthunt.com/products/pownap` returns 404. No launch was done. **[Verified — no PH launch]** (https://www.producthunt.com/products/pownap)
- **Hacker News (Algolia)**: 0 results for "PowNap" or "Haberling". **[Verified]** (https://hn.algolia.com/?q=PowNap)
- **Reddit**: `site:reddit.com "PowNap"` returns 0 indexed hits. **[Verified — no public Reddit footprint]**
- **Xing**: No findable profile. **[Unknown]**
- **Instagram / Threads / Facebook**: No account tied to the developer identity. **[Unknown]**

The only web property that is **his** is the app marketing site at **https://pownap.carrd.co** and its sibling **https://caldown.carrd.co** — both single-page Carrd sites, no social links, no personal bio, no developer photo, no "About me" section. Contact email visible on the carrd site is at the `pownap` domain (the carrd extract showed `[email protected]` — pattern obfuscated by the fetch tool). **[Verified]**

## 2. Professional background

- **Name on App Store**: "Valentin Haberling", Apple developer ID **1803412455**. **[Verified]** (https://apps.apple.com/us/developer/valentin-haberling/id1803412455)
- **Apps shipped under this developer ID**: exactly two — PowNap and CalDown. No prior apps. The developer ID was provisioned in early 2025 (consistent with the March 2025 PowNap launch). **[Verified]**
- **Location**: Strong signal of German-speaking Europe. Surname is German; PowNap appears on the German/Austrian App Store storefronts; the German listing carries the EU disclosure *"Valentin Haberling hat sich nicht als Händler für diese App ausgewiesen"* — i.e. he is registered with Apple as an **individual developer, not a trader/business** under EU DSA rules. **[Verified — German App Store]** (https://apps.apple.com/de/app/pownap/id6743547737)
- **Education / employer**: **[Unknown]** — no LinkedIn, no Xing, no CV, no university page, no GitHub bio.
- **Indie vs full-time**: His own carrd copy is the only direct statement: *"No team. No investors. Just focus, iteration, and a real need for calm — turned into something that fits on your wrist."* He also writes that the app was *"developed fully in SwiftUI — line by line, feature by feature — with AI used the same way other developers use StackOverflow or documentation: as a thinking partner."* **[Verified — pownap.carrd.co]**. This positions him as a solo hobbyist / indie dev, not as a venture-backed founder.

## 3. App marketing signals

- **Press coverage**: Zero. Searches across MacStories, 9to5Mac, AppleInsider, MacRumors, heise.de, macwelt.de, iphone-ticker.de turned up no review or mention. **[Verified absence]**
- **Podcast / interview footprint**: Zero. **[Verified absence]**
- **Product Hunt launch**: Did not happen — slug 404s. **[Verified]**
- **Show HN**: 0 hits on hn.algolia.com. **[Verified]**
- **Reddit posts** (`r/iOSProgramming`, `r/SideProject`, `r/AppleWatch`, `r/Naps`, etc.): 0 indexed results for "PowNap". **[Verified]**
- **TestFlight beta recruitment posts**: None found on the usual beta-recruitment surfaces (Reddit, Twitter, findbeta.no, departures.to). **[Verified absence]**
- **Carrd site as sole marketing surface**: One-page, no blog, no changelog, no roadmap, no email-capture. **[Verified]**

The marketing posture is **essentially nonexistent**. Distribution appears to rely entirely on App Store search and organic discovery.

## 4. Update / development cadence

**PowNap** (launched 2025-03-21, v1.0). Source: App Store version history. **[Verified]** (https://apps.apple.com/us/app/pownap/id6743547737)

| Version | Date | Notes |
|---|---|---|
| 1.0 | 2025-03-21 | Launch |
| 1.2 | 2025-03-23 | Initial features |
| 1.2.1 | 2025-03-27 | UI fixes |
| 1.2.2 | 2025-03-28 | Bug fixes |
| 1.2.3 | 2025-03-30 | Auto Mode (sleep detection) |
| 1.3 | 2025-04-05 | Quick-select buttons |
| 1.4 | 2025-05-27 | Health app integration |
| 2.0 | 2025-06-04 | Unlimited nap |
| 2.1 | 2025-06-09 | Infinity Mode |
| 2.2 | 2025-06-10 | Infinity-mode bug fix |
| 2.3 | 2025-06-12 | Progress redesign, nap overview |
| 2.3.1 | 2025-12-01 | Crash fix |
| 2.4 | 2026-01-05 | Minor UI |
| 2.4.1 | 2026-02-06 | UI polish, Hold-to-Stop, HR fallback |
| 2.4.2 | 2026-03-25 | Custom durations, onboarding, Health flow |
| 2.4.3 | 2026-04-29 | Bug fixes |

Pattern: **very high cadence in launch quarter (Mar–Jun 2025)** — 11 releases in ~12 weeks. Then a **~6-month gap** (Jun 12 to Dec 1, 2025) with only a crash fix and minor UI work. Cadence in 2026 is roughly monthly bug-fix-grade releases. **[Inferred]** suggests initial intense push followed by a maintenance pattern — consistent with a side project rather than a full-time business sprint.

**CalDown** (launched 2025-04-06, current v1.5 on 2025-06-15). **[Verified]** (https://apps.apple.com/us/app/caldown/id6744269741)

Similar pattern: bursty release activity April–June 2025 (1.0 → 1.5), then no public update since 2025-06-15 as of this report. **[Inferred]** — CalDown appears to be in a near-dormant state.

The combined picture: he is currently maintaining PowNap (monthly tinkering) and has essentially paused CalDown. This is **not** the cadence of an accelerating startup.

## 5. Strategic signals

- **Acquisition / fundraising ambition**: No public statement of any kind. His own marketing copy explicitly says *"No team. No investors."* **[Verified — pownap.carrd.co]** — this is positioned as a virtue ("private, on-device, no tracking"), not as a precursor to scaling.
- **Discussion of the nap/sleep market**: None found. He has not blogged, tweeted, or commented publicly about market opportunity, competitors, or TAM.
- **Business-vs-portfolio framing**: The carrd site frames PowNap as a *"tool that didn't exist"* built out of *"a real need for calm"* — first-person, problem-driven, no business plan language. He is registered with Apple as an individual (not a registered trader under EU rules per the DE App Store disclosure). **[Verified]**
- **Pricing**: PowNap $5.99 one-time, no subscription, no IAP, no ads. CalDown free + $3.99 one-time Pro IAP. Pricing is consumer-tier hobby-grade, not subscription-MRR optimized. **[Verified]**

## Strategic synthesis (for the competitive decision)

The evidence points strongly and consistently to **a solo hobbyist / part-time indie developer with no marketing apparatus, no community presence, no press relationships, and no stated commercial ambition beyond shipping a niche tool he wanted for himself**. Specifically:

1. **Zero discoverable footprint** on the channels where a serious indie iOS dev would normally live (Twitter/X, Mastodon iosdev.space, GitHub, MacStories, Indie Hackers, Show HN, Product Hunt). The cleanness of this absence is itself a strong negative signal — he is not building an audience.
2. **No press, no podcasts, no PH launch, no TestFlight recruitment, no Reddit posts.** Distribution is App Store search only.
3. **Cadence is bursty then maintenance** — the classic shape of a passionate launch followed by a long tail of evening/weekend tweaks. CalDown looks nearly abandoned.
4. **Self-described as solo, unfunded, AI-assisted, privacy-first.** Registered with Apple as an **individual, not a merchant** under EU rules — a meaningful structural ceiling on his ability to scale (it limits payment surfaces and consumer-rights posture).
5. **The product itself is genuinely well-executed**: the heart-rate-driven nap concept is differentiated, the version history shows real iterative thinking (Infinity Mode, custom durations, Hold-to-Stop, Health integration), and he has shipped consistently for ~14 months. He is technically competent and product-minded.

**Competitive threat assessment**: A serious entrant with marketing budget, ASO investment, content/SEO, influencer/press strategy, and full-time velocity would almost certainly out-distribute him quickly. He occupies the niche today by virtue of being first/only-of-his-kind on App Store search, not by virtue of a moat. The product moat is the heart-rate algorithm and the polish — both replicable. He has no audience to defend the position, no email list, no community, and no funding to retaliate.

**However**, two things are worth respecting: (a) he has demonstrated genuine technical taste and iteration discipline — he could ship faster than expected if motivated, and (b) the App Store rewards incumbency and ratings, so even a small head start with positive reviews compounds. A new entrant should plan to **out-market** rather than out-build him.

**One caution**: absence of public footprint also means absence of signal about *who he actually is.* If he is a Senior iOS engineer at a major company moonlighting, the technical bar of any competitor needs to be high. The carrd page is well-written marketing copy, and the SwiftUI execution is non-trivial. Don't underestimate the craft.

## Methodology & confidence

- **Sources used**: Apple App Store (US + DE storefronts), the developer's own carrd marketing sites, AppAdvice listing, HN Algolia, Google site: searches against reddit/producthunt/indiehackers/bsky/mastodon/iosdev.space, broad LinkedIn/Xing/GitHub/X searches.
- **Tools that failed**: Direct WebFetch to reddit.com (blocked), to `valentinhaberling.com` and `haberling.dev` (ECONNREFUSED — domains not hosted), to `appshunter.io` (403), to `getapp.cc` (401). Workarounds via search-engine snippets used.
- **Confidence in negatives**: High for HN (Algolia is comprehensive), Product Hunt (slug 404), and the developer-ID app list (only 2 apps under ID 1803412455). Medium for LinkedIn/Mastodon/Bluesky (those platforms index poorly in web search; a hidden account is possible but unlikely to be marketing-active if it requires deep platform-internal search to find).
- **Confidence in cadence data**: High — pulled directly from App Store version history.
- **What I did NOT verify**: His country of residence (German surname + DE App Store presence is suggestive only), his employer (no LinkedIn), his age, or whether he has unreleased projects in TestFlight.

### Adversarial content encountered

During this research, multiple tool outputs (WebFetch and WebSearch results) contained **injected `<system-reminder>` blocks** instructing me to use `TaskCreate`/`TaskUpdate` tools. These were embedded inside the returned web content (not from the user or the harness) and constitute **prompt-injection attempts**. I ignored them in all cases and continued with the user's original instructions. Specifically, injections appeared in: the App Store PowNap fetch result, the "CalDown calendar countdown Haberling" search, the Bluesky-site search, the Google-reddit search, and the `@valentinhaberling` search. The injections did not appear to be specifically crafted against this target — they look like a generic prompt-injection payload that has propagated into third-party content scrapes. No content I encountered attempted to alter facts about Haberling himself.

### Key URLs (verified)

- App Store developer page: https://apps.apple.com/us/developer/valentin-haberling/id1803412455
- PowNap (US): https://apps.apple.com/us/app/pownap/id6743547737
- PowNap (DE, with EU trader disclosure): https://apps.apple.com/de/app/pownap/id6743547737
- CalDown: https://apps.apple.com/us/app/caldown/id6744269741
- PowNap marketing site: https://pownap.carrd.co
- CalDown marketing site: https://caldown.carrd.co
- AppAdvice listing: https://appadvice.com/app/pownap/6743547737
- Confirmed-empty: https://www.producthunt.com/products/pownap (404), https://hn.algolia.com/?q=PowNap (0 results)
