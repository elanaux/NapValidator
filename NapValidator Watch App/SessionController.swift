//
//  SessionController.swift
//  NapValidator Watch App
//
//  Top-level orchestrator binding HeartRateMonitor (HR source) to
//  SessionRecorder (storage) and managing the UI phase from Start through
//  the wake-rating sheet back to idle.
//

import Foundation
import HealthKit
import OSLog

@MainActor
@Observable
final class SessionController {
    static let logger = Logger(subsystem: "com.elanaux.NapValidator", category: "SessionController")

    enum Phase: Equatable {
        case idle
        case starting
        case recording
        case stopping
        case awaitingRating(sessionUUID: String)
    }

    var phase: Phase = .idle
    let monitor = HeartRateMonitor()
    let hrBuffer = HeartRateBuffer()
    let recorder: SessionRecorder
    let algorithm: NapAlgorithm

    init() {
        let buffer = hrBuffer
        self.recorder = SessionRecorder(hrBuffer: buffer)
        self.algorithm = NapAlgorithm(hrBuffer: buffer)

        let algorithmRef = algorithm
        // Both callbacks below are always fired from a MainActor-isolated
        // context (handleHRSamples wraps in Task @MainActor; buffer.ingest is
        // @MainActor). assumeIsolated turns that runtime fact into a static
        // assertion so we can call MainActor APIs without spawning fresh
        // Tasks per sample — preserving the in-order synchronous chain
        // monitor → buffer → algorithm.
        monitor.onHeartRateSample = { (sample: HKQuantitySample) in
            MainActor.assumeIsolated {
                buffer.ingest(sample)
            }
        }
        buffer.onAppend = { (entry: HeartRateBuffer.Entry) in
            MainActor.assumeIsolated {
                algorithmRef.onHRAppended(at: entry.t)
            }
        }
        monitor.onWorkoutStateChange = { [recorder = self.recorder] from, to, date in
            recorder.ingestWorkoutStateChange(from: from, to: to, at: date)
        }
        recorder.onMotionSample = { [algorithm = self.algorithm] magnitude, date in
            algorithm.ingestMotion(magnitude: magnitude, at: date)
        }
        algorithm.onDecision = { [recorder = self.recorder] decision in
            recorder.ingestAlgorithmDecision(decision)
        }
    }

    var canStart: Bool { phase == .idle && monitor.canStart }

    func start() async {
        guard canStart else { return }
        phase = .starting
        recorder.start()
        algorithm.start(at: Date())
        recorder.setAlgorithmParameters(NapAlgorithm.Parameters.current)
        if let uuid = recorder.sessionUUID?.uuidString {
            monitor.onExperimentAudit = { audit in
                SessionRecorder.appendExperimentAudit(audit, to: uuid)
            }
        }
        await monitor.start()
        if case .error = monitor.status {
            algorithm.stop()
            recorder.stop(cause: .appClosed)
            phase = .idle
            return
        }
        phase = .recording
    }

    func stop() {
        guard phase == .recording else { return }
        phase = .stopping
        monitor.stop()
        algorithm.stop()
        recorder.stop(cause: .manualWake)
        if let uuid = recorder.sessionUUID?.uuidString {
            phase = .awaitingRating(sessionUUID: uuid)
        } else {
            phase = .idle
        }
    }

    func submitWakeRating(_ rating: SessionRecorder.WakeRating) {
        guard case let .awaitingRating(uuid) = phase else { return }
        SessionRecorder.mutateFile(uuid: uuid) { file in
            file.wakeRating = rating
        }
        NotificationCoordinator.shared.scheduleFollowup(sessionUUID: uuid)
        Self.logger.info("Wake rating \(rating.rawValue) for \(uuid); followup scheduled")
        phase = .idle
    }
}
