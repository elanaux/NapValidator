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

    // Legacy hook retained for interface stability. The buffer-aware path uses
    // onHeartRateSample below to carry the HKQuantitySample (and its uuid) for
    // identity-based dedup. Both fire from the anchored-query handler.
    var onHeartRate: ((Double, Date) -> Void)?
    var onHeartRateSample: ((HKQuantitySample) -> Void)?
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
    private var hrQuery: HKAnchoredObjectQuery?
    private let bpmUnit = HKUnit.count().unitDivided(by: .minute())

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

            session.pause()
            Self.logger.info("Paused session immediately after start to suppress ring credits (pausedImmediately=true)")

            await startHRAnchoredQuery(from: startDate)

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
        stopHRAnchoredQuery()
        session.end()

        Task {
            var finishedWorkout: HKWorkout?
            do {
                try await builder.endCollection(at: endDate)
                finishedWorkout = try await builder.finishWorkout()
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
                    pausedImmediately: true,
                    activeEnergyBurnedSampleCount: energy.count,
                    activeEnergyBurnedTotalKcal: energy.total,
                    appleExerciseTimeSampleCount: exercise.count,
                    appleExerciseTimeTotalMinutes: exercise.total
                )
                Self.logger.info("Audit: kcal=\(energy.total) (n=\(energy.count)) exerciseMin=\(exercise.total) (n=\(exercise.count))")
                self.onExperimentAudit?(audit)
            }

            // Delete the workout entry from HealthKit. Workout objects ARE
            // third-party-deletable (unlike activeEnergyBurned / appleExerciseTime,
            // which we deliberately do not touch — they're non-third-party-
            // deletable and near-zero under paused mode anyway). Audit above
            // already captured their counts/totals, so deletion here doesn't
            // race with the audit. The intent is to keep the Fitness app's
            // workout list clean: paused mode validated ~0 ring credit, so the
            // workout entry no longer serves as a user-visible audit record.
            if let workout = finishedWorkout {
                let result = await self.deleteWorkout(workout)
                if result.success {
                    Self.logger.info("Workout deleted on stop: success uuid=\(workout.uuid.uuidString)")
                } else {
                    let reason = result.error?.localizedDescription ?? "unknown error"
                    Self.logger.error("Workout deleted on stop: failure (\(reason))")
                }
            } else {
                Self.logger.error("Workout deleted on stop: failure (no workout returned from finishWorkout)")
            }

            self.session = nil
            self.builder = nil
            self.sessionStartDate = nil
            self.status = .idle
        }
    }

    private func startHRAnchoredQuery(from startDate: Date) async {
        let heartRateType = HKQuantityType.quantityType(forIdentifier: .heartRate)!
        let datePredicate = HKQuery.predicateForSamples(withStart: startDate, end: nil, options: .strictStartDate)

        // Resolve the Apple Watch's HKSource by enumerating HR-writing sources.
        // Designed to fail safe: if resolution is ambiguous (multiple watches
        // paired, or locale/name mismatch), fall back to unfiltered rather
        // than risk an over-restrictive predicate that starves the algorithm.
        // The two log lines below distinguish the two paths so the console
        // tells us at a glance whether the filter actually engaged.
        let predicate: NSPredicate
        if let watchSource = await resolveWatchHRSource() {
            let sourcePredicate = HKQuery.predicateForObjects(from: [watchSource])
            predicate = NSCompoundPredicate(andPredicateWithSubpredicates: [datePredicate, sourcePredicate])
            Self.logger.info("HR source filter applied: source=\(watchSource.name) bundle=\(watchSource.bundleIdentifier)")
        } else {
            predicate = datePredicate
            Self.logger.info("HR source filter UNAVAILABLE, running unfiltered")
        }

        let query = HKAnchoredObjectQuery(
            type: heartRateType,
            predicate: predicate,
            anchor: nil,
            limit: HKObjectQueryNoLimit
        ) { [weak self] _, samples, _, _, error in
            if let error {
                Self.logger.error("HR anchored initial: \(error.localizedDescription)")
                return
            }
            self?.deliverHRSamples(samples)
        }
        query.updateHandler = { [weak self] _, samples, _, _, error in
            if let error {
                Self.logger.error("HR anchored update: \(error.localizedDescription)")
                return
            }
            self?.deliverHRSamples(samples)
        }
        healthStore.execute(query)
        hrQuery = query
        Self.logger.info("HR anchored query started predicate>=\(startDate.timeIntervalSince1970)")
    }

    /// Returns the HKSource representing this Apple Watch's HR sensor, or nil
    /// when the watch source cannot be unambiguously identified. The caller
    /// must treat nil as "run unfiltered" — never as "filter to nothing."
    ///
    /// Strategy: identify the watch by inspecting a recent HR sample's HKDevice
    /// (hardwareVersion / model), then return that sample's source. This
    /// decouples source identity from name-string matching — `hardwareVersion`
    /// is a firmware identifier ("Watch7,5", etc.), stable across locale and
    /// user rename. Previous name-substring approach failed because Apple
    /// embeds a non-breaking space (U+00A0) in "Apple Watch", which doesn't
    /// equal an ASCII-space literal of the same visible text.
    private func resolveWatchHRSource() async -> HKSource? {
        let heartRateType = HKQuantityType.quantityType(forIdentifier: .heartRate)!
        let recentPredicate = HKQuery.predicateForSamples(
            withStart: Date().addingTimeInterval(-3600),
            end: nil,
            options: []
        )
        let sortDescriptor = NSSortDescriptor(key: HKSampleSortIdentifierEndDate, ascending: false)
        return await withCheckedContinuation { continuation in
            let query = HKSampleQuery(
                sampleType: heartRateType,
                predicate: recentPredicate,
                limit: 20,
                sortDescriptors: [sortDescriptor]
            ) { _, samples, error in
                if let error {
                    Self.logger.error("HR source resolution sample query failed: \(error.localizedDescription)")
                    continuation.resume(returning: nil)
                    return
                }
                let quantitySamples = (samples as? [HKQuantitySample]) ?? []
                if let watchSample = quantitySamples.first(where: { Self.isWatchDevice($0.device) }) {
                    let source = watchSample.sourceRevision.source
                    Self.logger.info("HR source resolved via recent sample: source=\(source.name) device.hw=\(watchSample.device?.hardwareVersion ?? "?") device.model=\(watchSample.device?.model ?? "?")")
                    continuation.resume(returning: source)
                    return
                }
                let summary = quantitySamples.prefix(5).map { s -> String in
                    let hw = s.device?.hardwareVersion ?? "?"
                    let model = s.device?.model ?? "?"
                    return "[hw=\(hw) model=\(model) source=\(s.sourceRevision.source.name)]"
                }.joined(separator: " ")
                Self.logger.info("HR source resolution: no watch-device sample found among \(quantitySamples.count) recent; first5=\(summary)")
                continuation.resume(returning: nil)
            }
            self.healthStore.execute(query)
        }
    }

    /// True when an HKDevice looks like an Apple Watch HR sensor. We check the
    /// firmware-reported hardwareVersion ("Watch7,5", etc.) and model fields
    /// independently, since their exact population varies across watchOS
    /// versions. Either signal is sufficient.
    private static func isWatchDevice(_ device: HKDevice?) -> Bool {
        guard let device else { return false }
        if let hw = device.hardwareVersion, hw.hasPrefix("Watch") {
            return true
        }
        if let model = device.model, model == "Watch" {
            return true
        }
        return false
    }

    private func stopHRAnchoredQuery() {
        if let hrQuery {
            healthStore.stop(hrQuery)
            Self.logger.info("HR anchored query stopped")
        }
        hrQuery = nil
    }

    nonisolated private func deliverHRSamples(_ raw: [HKSample]?) {
        guard let quantitySamples = raw as? [HKQuantitySample], !quantitySamples.isEmpty else { return }
        // Process in chronological order so the algorithm's `evaluate(now:)`
        // sees monotonically advancing timestamps within a batch.
        let sorted = quantitySamples.sorted { $0.endDate < $1.endDate }
        let bpmUnit = self.bpmUnit
        Task { @MainActor [weak self] in
            guard let self else { return }
            for sample in sorted {
                let bpm = sample.quantity.doubleValue(for: bpmUnit)
                self.sampleCount += 1
                self.latestHeartRate = bpm
                self.latestSampleDate = sample.endDate
                self.onHeartRateSample?(sample)
                self.onHeartRate?(bpm, sample.endDate)
                Self.logger.info("HR sample t=\(sample.endDate.timeIntervalSince1970) bpm=\(bpm) uuid=\(sample.uuid.uuidString)")
            }
        }
    }

    private func deleteWorkout(_ workout: HKWorkout) async -> (success: Bool, error: Error?) {
        await withCheckedContinuation { continuation in
            healthStore.delete(workout) { success, error in
                continuation.resume(returning: (success, error))
            }
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
        // HR is now ingested via HKAnchoredObjectQuery in start(). The workout
        // session is still required to keep the watch's HR sensor at the live
        // sampling rate, but we no longer read HR from the builder's cached
        // statistics — that path was the source of the timestamp collapse.
    }

    nonisolated func workoutBuilderDidCollectEvent(_ workoutBuilder: HKLiveWorkoutBuilder) {
        // Required by HKLiveWorkoutBuilderDelegate. No event-level handling needed for this spike.
    }
}
