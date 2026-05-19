//
//  SessionController.swift
//  NapValidator Watch App
//
//  Top-level orchestrator binding HeartRateMonitor (HR source) to
//  SessionRecorder (storage) and managing the UI phase from Start through
//  the wake-rating sheet back to idle.
//

import Foundation
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
    let recorder = SessionRecorder()
    let algorithm = NapAlgorithm()

    init() {
        monitor.onHeartRate = { [recorder, algorithm] bpm, date in
            recorder.ingestHeartRate(bpm: bpm, at: date)
            algorithm.ingestHR(bpm: bpm, at: date)
        }
        monitor.onWorkoutStateChange = { [recorder] from, to, date in
            recorder.ingestWorkoutStateChange(from: from, to: to, at: date)
        }
        recorder.onMotionSample = { [algorithm] magnitude, date in
            algorithm.ingestMotion(magnitude: magnitude, at: date)
        }
        algorithm.onDecision = { [recorder] decision in
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
