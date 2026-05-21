# Claude Code — Standing Instructions for NapValidator

## Deployment (CRITICAL)
- NEVER deploy or run on a physical device or simulator. Build-to-compile only.
- Do NOT run `devicectl`, `xcrun simctl ... launch`, or any install/launch command.
- I deploy to my Apple Watch via Xcode myself. "BUILD SUCCEEDED" is your finish line.
- Rationale: a build succeeding does not prove the running binary behaves correctly. I verify on-device myself, and session JSON build markers confirm which code actually ran.

## Changes to product-spine code
- For changes to capture, algorithm, or recording logic: explain the change and confirm it compiles, but assume I will review and verify on-device before it's trusted. Do not describe unverified changes as "working" or "validated" — only as "built / compiles."
- Bump the build marker in Build.swift when a change should be distinguishable in session JSON, so I can confirm which build produced a dataset.

## Data
- NEVER delete diagnostic or session data (session JSONs, exports, recovered files). Move/archive if needed, never `rm`. Smoke-test sessions live in sessions/smoke_tests/.
- The current Apple Health export is the most recent one on the Desktop — confirm its ExportDate before parsing; never assume.
- Large files (export.xml ~1GB): always stream-parse (iterparse + clear), never load whole into memory.

## Verification discipline
- Print a summary/verification table BEFORE writing analysis output or drawing conclusions, so results can be sanity-checked before they're built on.
- Distinguish "shape/structural" findings from "parameter" findings; never recommend parameter values from deprived-physiology or n-small data.

## Project context
- See PRODUCT.md (repo root) for current-truth product state, architecture (Section 3), and open questions. PRODUCT.md is the single source of truth — read it rather than inferring project state.