//
//  Build.swift
//  NapValidator Watch App
//
//  Self-identifying build marker. Bump `marker` whenever a meaningful
//  ingestion / algorithm / capture change ships, so every session JSON
//  carries the version of the code that actually produced it. Independent
//  of CFBundleShortVersionString / Info.plist — those track release
//  versioning; this tracks "which experimental code path."
//

enum Build {
    static let marker = "v0.2.0 2026-05-21"
}
