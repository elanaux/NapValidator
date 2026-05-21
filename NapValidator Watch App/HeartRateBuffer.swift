//
//  HeartRateBuffer.swift
//  NapValidator Watch App
//
//  Single shared in-memory HR sample store. Both the algorithm's windowed
//  reads and the recorder's persisted output draw from this one buffer,
//  replacing the prior design in which SessionRecorder and NapAlgorithm
//  each maintained independent arrays populated from separate
//  Task { @MainActor } enqueues — those could diverge by a sample at a
//  window boundary.
//
//  Dedup is identity-based on HKQuantitySample.uuid as defense-in-depth.
//  HKAnchoredObjectQuery already yields each fresh sample exactly once via
//  its anchor mechanism, so in practice the seenIDs set should never fire.
//

import Foundation
import HealthKit

@MainActor
final class HeartRateBuffer {
    struct Entry {
        let id: UUID
        let t: TimeInterval
        let bpm: Double
    }

    private(set) var entries: [Entry] = []
    private var seenIDs: Set<UUID> = []
    private let bpmUnit = HKUnit.count().unitDivided(by: .minute())

    var onAppend: ((Entry) -> Void)?

    func ingest(_ sample: HKQuantitySample) {
        guard !seenIDs.contains(sample.uuid) else { return }
        seenIDs.insert(sample.uuid)
        let entry = Entry(
            id: sample.uuid,
            t: sample.endDate.timeIntervalSince1970,
            bpm: sample.quantity.doubleValue(for: bpmUnit)
        )
        entries.append(entry)
        onAppend?(entry)
    }

    func reset() {
        entries.removeAll()
        seenIDs.removeAll()
    }
}
