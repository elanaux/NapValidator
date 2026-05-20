//
//  HeartRateMonitor.swift
//  NapValidator Watch App
//
//  Drives an HKWorkoutSession + HKLiveWorkoutBuilder configured for
//  .mindAndBody so we can measure whether active sessions deliver
//  meaningfully higher heart-rate sample frequency than passive HealthKit.
//

import Foundation
import HealthKit
import OSLog

@Observable
final class HeartRateMonitor: NSObject {
    static let logger = Logger(subsystem: "com.elanaux.NapValidator", category: "HeartRate")

    enum Status: Equatable {
        case idle
        case authorizing
        case running
        case stopping
        case error(String)

        var description: String {
            switch self {
            case .idle: return "Idle"
            case .authorizing: return "Authorizing…"
            case .running: return "Running"
            case .stopping: return "Stopping…"
            case .error(let message): return "Error: \(message)"
            }
        }
    }

    var sampleCount: Int = 0
    var latestHeartRate: Double?
    var latestSampleDate: Date?
    var status: Status = .idle

    var onHeartRate: ((Double, Date) -> Void)?
    var onWorkoutStateChange: ((String, String, Date) -> Void)?
    var onExperimentAudit: ((SessionRecorder.ExperimentAudit) -> Void)?

    nonisolated static func stateName(_ state: HKWorkoutSessionState) -> String {
        switch state {
        case .notStarted: return "notStarted"
        case .running: return "running"
        case .ended: return "ended"
        case .paused: return "paused"
        case .prepared: return "prepared"
        case .stopped: return "stopped"
        @unknown default: return "unknown(\(state.rawValue))"
        }
    }

    var isRunning: Bool { status == .running }
    var canStart: Bool {
        switch status {
        case .idle, .error: return true
        default: return false
        }
    }

    private let healthStore = HKHealthStore()
    private var session: HKWorkoutSession?
    private var builder: HKLiveWorkoutBuilder?
    private var sessionStartDate: Date?

    func start() async {
        guard HKHealthStore.isHealthDataAvailable() else {
            status = .error("HealthKit unavailable on this device")
            return
        }

        status = .authorizing

        let heartRateType = HKQuantityType.quantityType(forIdentifier: .heartRate)!
        let activeEnergyType = HKQuantityType.quantityType(forIdentifier: .activeEnergyBurned)!
        let exerciseTimeType = HKQuantityType.quantityType(forIdentifier: .appleExerciseTime)!
        let typesToRead: Set<HKObjectType> = [
            heartRateType,
            activeEnergyType, exerciseTimeType,
            HKObjectType.workoutType()
        ]
        let typesToShare: Set<HKSampleType> = [HKObjectType.workoutType(), activeEnergyType]

        do {
            try await healthStore.requestAuthorization(toShare: typesToShare, read: typesToRead)
        } catch {
            status = .error("Auth failed: \(error.localizedDescription)")
            return
        }

        let configuration = HKWorkoutConfiguration()
        configuration.activityType = .other
        configuration.locationType = .indoor

        do {
            let session = try HKWorkoutSession(healthStore: healthStore, configuration: configuration)
            let builder = session.associatedWorkoutBuilder()
            builder.dataSource = HKLiveWorkoutDataSource(
                healthStore: healthStore,
                workoutConfiguration: configuration
            )

            session.delegate = self
            builder.delegate = self

            self.session = session
            self.builder = builder

            let startDate = Date()
            sessionStartDate = startDate

            sampleCount = 0
            latestHeartRate = nil
            latestSampleDate = nil

            session.startActivity(with: startDate)
            try await builder.beginCollection(at: startDate)

            status = .running
            Self.logger.info("Workout session started at t=\(startDate.timeIntervalSince1970)")
        } catch {
            status = .error("Start failed: \(error.localizedDescription)")
        }
    }

    func stop() {
        guard let session, let builder else { return }
        status = .stopping

        let endDate = Date()
        let auditStartDate = sessionStartDate
        session.end()

        Task {
            do {
                try await builder.endCollection(at: endDate)
                _ = try await builder.finishWorkout()
                Self.logger.info("Workout session ended at t=\(endDate.timeIntervalSince1970). Total samples: \(self.sampleCount)")
            } catch {
                Self.logger.error("End workout failed: \(error.localizedDescription)")
            }

            if let auditStartDate {
                let activeEnergyType = HKQuantityType.quantityType(forIdentifier: .activeEnergyBurned)!
                let exerciseTimeType = HKQuantityType.quantityType(forIdentifier: .appleExerciseTime)!
                let energy = await self.querySumAndCount(type: activeEnergyType, unit: .kilocalorie(), start: auditStartDate, end: endDate)
                let exercise = await self.querySumAndCount(type: exerciseTimeType, unit: .minute(), start: auditStartDate, end: endDate)
                let audit = SessionRecorder.ExperimentAudit(
                    pausedImmediately: false,
                    activeEnergyBurnedSampleCount: energy.count,
                    activeEnergyBurnedTotalKcal: energy.total,
                    appleExerciseTimeSampleCount: exercise.count,
                    appleExerciseTimeTotalMinutes: exercise.total
                )
                Self.logger.info("Audit: kcal=\(energy.total) (n=\(energy.count)) exerciseMin=\(exercise.total) (n=\(exercise.count))")
                self.onExperimentAudit?(audit)
            }

            self.session = nil
            self.builder = nil
            self.sessionStartDate = nil
            self.status = .idle
        }
    }

    private func querySumAndCount(type: HKQuantityType, unit: HKUnit, start: Date, end: Date) async -> (count: Int, total: Double) {
        let predicate = HKQuery.predicateForSamples(withStart: start, end: end, options: [])
        return await withCheckedContinuation { continuation in
            let query = HKSampleQuery(sampleType: type, predicate: predicate, limit: HKObjectQueryNoLimit, sortDescriptors: nil) { _, samples, error in
                if let error {
                    Self.logger.error("Experiment query failed for \(type.identifier): \(error.localizedDescription)")
                    continuation.resume(returning: (0, 0))
                    return
                }
                let quantitySamples = (samples as? [HKQuantitySample]) ?? []
                let total = quantitySamples.reduce(0.0) { $0 + $1.quantity.doubleValue(for: unit) }
                continuation.resume(returning: (quantitySamples.count, total))
            }
            self.healthStore.execute(query)
        }
    }

}

extension HeartRateMonitor: HKWorkoutSessionDelegate {
    nonisolated func workoutSession(_ workoutSession: HKWorkoutSession,
                                    didChangeTo toState: HKWorkoutSessionState,
                                    from fromState: HKWorkoutSessionState,
                                    date: Date) {
        let from = Self.stateName(fromState)
        let to = Self.stateName(toState)
        Self.logger.info("Session state \(from) -> \(to) at t=\(date.timeIntervalSince1970)")
        Task { @MainActor [weak self] in
            self?.onWorkoutStateChange?(from, to, date)
        }
    }

    nonisolated func workoutSession(_ workoutSession: HKWorkoutSession, didFailWithError error: Error) {
        let message = error.localizedDescription
        Self.logger.error("Session failed: \(message)")
        Task { @MainActor [weak self] in
            self?.status = .error(message)
        }
    }
}

extension HeartRateMonitor: HKLiveWorkoutBuilderDelegate {
    nonisolated func workoutBuilder(_ workoutBuilder: HKLiveWorkoutBuilder,
                                    didCollectDataOf collectedTypes: Set<HKSampleType>) {
        let heartRateType = HKQuantityType.quantityType(forIdentifier: .heartRate)!
        guard collectedTypes.contains(heartRateType) else { return }
        guard let stats = workoutBuilder.statistics(for: heartRateType),
              let recent = stats.mostRecentQuantity() else { return }

        let bpmUnit = HKUnit.count().unitDivided(by: .minute())
        let bpm = recent.doubleValue(for: bpmUnit)
        let timestamp = stats.mostRecentQuantityDateInterval()?.end ?? Date()

        Self.logger.info("HR sample t=\(timestamp.timeIntervalSince1970) bpm=\(bpm)")

        Task { @MainActor [weak self] in
            guard let self else { return }
            self.sampleCount += 1
            self.latestHeartRate = bpm
            self.latestSampleDate = timestamp
            self.onHeartRate?(bpm, timestamp)
        }
    }

    nonisolated func workoutBuilderDidCollectEvent(_ workoutBuilder: HKLiveWorkoutBuilder) {
        // Required by HKLiveWorkoutBuilderDelegate. No event-level handling needed for this spike.
    }
}
