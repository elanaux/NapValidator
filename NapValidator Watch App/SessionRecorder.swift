//
//  SessionRecorder.swift
//  NapValidator Watch App
//
//  Owns the full session lifecycle: identity, timing, motion sampling,
//  screen/orientation events, and ingestion of HR samples from
//  HeartRateMonitor. Serializes a per-session JSON file into the app's
//  Documents directory, with periodic partial flushes for crash recovery.
//

import Foundation
import CoreMotion
import WatchKit
import OSLog

@MainActor
@Observable
final class SessionRecorder {
    static let logger = Logger(subsystem: "com.elanaux.NapValidator", category: "SessionRecorder")

    enum EndCause: String, Codable {
        case manualWake = "manual_wake"
        case backbyFired = "backby_fired"
        case appClosed = "app_closed"
    }

    enum WakeRating: String, Codable, CaseIterable, Identifiable {
        case sharp, fine, groggy, worse
        var id: String { rawValue }
        var label: String {
            switch self {
            case .sharp: return "Sharp"
            case .fine: return "Fine"
            case .groggy: return "Groggy"
            case .worse: return "Worse"
            }
        }
    }

    enum FollowupRating: String, Codable, CaseIterable {
        case stillFocused = "still_focused"
        case wearingOff = "wearing_off"
        case alreadyWornOff = "already_worn_off"
        case crashed
        var label: String {
            switch self {
            case .stillFocused: return "Still focused"
            case .wearingOff: return "Wearing off"
            case .alreadyWornOff: return "Already worn off"
            case .crashed: return "I crashed"
            }
        }
    }

    enum WristOrientation: String, Codable {
        case up, down
    }

    struct HRSample: Codable { let t: TimeInterval; let bpm: Double }
    struct MotionSample: Codable {
        let t: TimeInterval
        let gx: Double; let gy: Double; let gz: Double
        let ax: Double; let ay: Double; let az: Double
    }
    struct ScreenEvent: Codable { let t: TimeInterval; let type: String }
    struct WristEvent: Codable { let t: TimeInterval; let orientation: WristOrientation }
    struct WorkoutStateEvent: Codable { let t: TimeInterval; let from: String; let to: String }
    struct ExperimentAudit: Codable {
        let pausedImmediately: Bool
        let activeEnergyBurnedSampleCount: Int
        let activeEnergyBurnedTotalKcal: Double
        let appleExerciseTimeSampleCount: Int
        let appleExerciseTimeTotalMinutes: Double
    }

    struct SessionFile: Codable {
        let sessionUUID: String
        // Optional so older session files written before this field existed
        // still decode (via mutateFile / loadFile). New sessions always set it.
        var buildMarker: String?
        let startTimestamp: TimeInterval
        var endTimestamp: TimeInterval?
        var endCause: EndCause?
        let batteryStart: Float
        var batteryEnd: Float?
        var heartRateSamples: [HRSample]
        var motionSamples: [MotionSample]
        var screenEvents: [ScreenEvent]
        var wristOrientationEvents: [WristEvent]
        var workoutStateEvents: [WorkoutStateEvent]
        var experimentAudit: ExperimentAudit?
        var wakeRating: WakeRating?
        var followupRating: FollowupRating?
        var followupRespondedAt: TimeInterval?
        var algorithmDecisions: [NapAlgorithm.Decision]?
        var algorithmParameters: NapAlgorithm.Parameters?
    }

    private(set) var isRunning = false
    private(set) var sessionUUID: UUID?

    var onMotionSample: ((Double, Date) -> Void)?

    private let hrBuffer: HeartRateBuffer
    private var startDate: Date?
    private var batteryStart: Float = 0
    private var motionSamples: [MotionSample] = []
    private var screenEvents: [ScreenEvent] = []
    private var wristEvents: [WristEvent] = []
    private var workoutStateEvents: [WorkoutStateEvent] = []
    private var algorithmDecisions: [NapAlgorithm.Decision] = []
    private var algorithmParameters: NapAlgorithm.Parameters?
    private var lastWristOrientation: WristOrientation?
    private var bootWallClock: TimeInterval = 0

    init(hrBuffer: HeartRateBuffer) {
        self.hrBuffer = hrBuffer
    }

    private let motionManager = CMMotionManager()
    private let motionQueue: OperationQueue = {
        let q = OperationQueue()
        q.name = "com.elanaux.NapValidator.motion"
        q.qualityOfService = .utility
        return q
    }()
    private var partialFlushTask: Task<Void, Never>?
    private var activateObserver: NSObjectProtocol?
    private var deactivateObserver: NSObjectProtocol?

    func start() {
        guard !isRunning else { return }

        let uuid = UUID()
        sessionUUID = uuid
        let now = Date()
        startDate = now
        hrBuffer.reset()
        motionSamples.removeAll()
        screenEvents.removeAll()
        wristEvents.removeAll()
        workoutStateEvents.removeAll()
        algorithmDecisions.removeAll()
        algorithmParameters = nil
        lastWristOrientation = nil
        bootWallClock = Date().timeIntervalSince1970 - ProcessInfo.processInfo.systemUptime

        WKInterfaceDevice.current().isBatteryMonitoringEnabled = true
        batteryStart = WKInterfaceDevice.current().batteryLevel

        startMotionUpdates()
        observeAppLifecycle()
        startPartialFlush()

        isRunning = true
        Self.logger.info("Session \(uuid.uuidString) started at t=\(now.timeIntervalSince1970), batteryStart=\(self.batteryStart), build=\(Build.marker)")
    }

    func stop(cause: EndCause) {
        guard isRunning else { return }
        let endDate = Date()
        WKInterfaceDevice.current().isBatteryMonitoringEnabled = true
        let batteryEnd = WKInterfaceDevice.current().batteryLevel

        stopMotionUpdates()
        stopObservingAppLifecycle()
        partialFlushTask?.cancel()
        partialFlushTask = nil

        writeFinal(endDate: endDate, endCause: cause, batteryEnd: batteryEnd)
        isRunning = false
        Self.logger.info("Session \(self.sessionUUID?.uuidString ?? "?") stopped cause=\(cause.rawValue) batteryEnd=\(batteryEnd)")
    }

    nonisolated func ingestWorkoutStateChange(from: String, to: String, at date: Date) {
        let event = WorkoutStateEvent(t: date.timeIntervalSince1970, from: from, to: to)
        Task { @MainActor [weak self] in
            self?.workoutStateEvents.append(event)
        }
    }

    nonisolated func ingestAlgorithmDecision(_ decision: NapAlgorithm.Decision) {
        Task { @MainActor [weak self] in
            self?.algorithmDecisions.append(decision)
        }
    }

    nonisolated func setAlgorithmParameters(_ params: NapAlgorithm.Parameters) {
        Task { @MainActor [weak self] in
            self?.algorithmParameters = params
        }
    }

    func recordWakeRating(_ rating: WakeRating) -> String? {
        guard let uuid = sessionUUID?.uuidString else { return nil }
        Self.mutateFile(uuid: uuid) { file in
            file.wakeRating = rating
        }
        return uuid
    }

    private func startMotionUpdates() {
        guard motionManager.isDeviceMotionAvailable else {
            Self.logger.error("Device motion unavailable")
            return
        }
        motionManager.deviceMotionUpdateInterval = 0.2
        let bootWallClock = self.bootWallClock
        motionManager.startDeviceMotionUpdates(to: motionQueue) { [weak self] motion, error in
            guard let self, let motion else { return }
            if let error {
                Self.logger.error("Motion error: \(error.localizedDescription)")
                return
            }
            let t = bootWallClock + motion.timestamp
            let sample = MotionSample(
                t: t,
                gx: motion.gravity.x, gy: motion.gravity.y, gz: motion.gravity.z,
                ax: motion.userAcceleration.x, ay: motion.userAcceleration.y, az: motion.userAcceleration.z
            )
            let orientation: WristOrientation = motion.gravity.z < -0.5 ? .down : .up
            let magnitude = (sample.ax * sample.ax + sample.ay * sample.ay + sample.az * sample.az).squareRoot()
            let sampleDate = Date(timeIntervalSince1970: t)

            Task { @MainActor [weak self] in
                guard let self else { return }
                self.motionSamples.append(sample)
                if orientation != self.lastWristOrientation {
                    self.lastWristOrientation = orientation
                    self.wristEvents.append(WristEvent(t: t, orientation: orientation))
                }
                self.onMotionSample?(magnitude, sampleDate)
            }
        }
    }

    private func stopMotionUpdates() {
        if motionManager.isDeviceMotionActive {
            motionManager.stopDeviceMotionUpdates()
        }
    }

    private func observeAppLifecycle() {
        let nc = NotificationCenter.default
        activateObserver = nc.addObserver(forName: WKApplication.didBecomeActiveNotification,
                                          object: nil, queue: .main) { [weak self] _ in
            Task { @MainActor [weak self] in
                self?.screenEvents.append(ScreenEvent(t: Date().timeIntervalSince1970, type: "wake"))
            }
        }
        deactivateObserver = nc.addObserver(forName: WKApplication.willResignActiveNotification,
                                            object: nil, queue: .main) { [weak self] _ in
            Task { @MainActor [weak self] in
                self?.screenEvents.append(ScreenEvent(t: Date().timeIntervalSince1970, type: "sleep"))
            }
        }
    }

    private func stopObservingAppLifecycle() {
        let nc = NotificationCenter.default
        if let activateObserver { nc.removeObserver(activateObserver) }
        if let deactivateObserver { nc.removeObserver(deactivateObserver) }
        activateObserver = nil
        deactivateObserver = nil
    }

    private func startPartialFlush() {
        partialFlushTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(30))
                if Task.isCancelled { break }
                await self?.writePartial()
            }
        }
    }

    private func snapshot(endDate: Date? = nil,
                          endCause: EndCause? = nil,
                          batteryEnd: Float? = nil) -> SessionFile? {
        guard let sessionUUID, let startDate else { return nil }
        let hrSamples = hrBuffer.entries.map { HRSample(t: $0.t, bpm: $0.bpm) }
        return SessionFile(
            sessionUUID: sessionUUID.uuidString,
            buildMarker: Build.marker,
            startTimestamp: startDate.timeIntervalSince1970,
            endTimestamp: endDate?.timeIntervalSince1970,
            endCause: endCause,
            batteryStart: batteryStart,
            batteryEnd: batteryEnd,
            heartRateSamples: hrSamples,
            motionSamples: motionSamples,
            screenEvents: screenEvents,
            wristOrientationEvents: wristEvents,
            workoutStateEvents: workoutStateEvents,
            experimentAudit: nil,
            wakeRating: nil,
            followupRating: nil,
            followupRespondedAt: nil,
            algorithmDecisions: algorithmDecisions,
            algorithmParameters: algorithmParameters
        )
    }

    private func writePartial() {
        guard let file = snapshot() else { return }
        Self.write(file: file)
    }

    private func writeFinal(endDate: Date, endCause: EndCause, batteryEnd: Float) {
        guard let file = snapshot(endDate: endDate, endCause: endCause, batteryEnd: batteryEnd) else { return }
        Self.write(file: file)
    }
}

extension SessionRecorder {
    static func documentsDirectory() -> URL {
        FileManager.default.urls(for: .documentDirectory, in: .userDomainMask).first!
    }

    static func fileURL(for file: SessionFile) -> URL {
        let startDate = Date(timeIntervalSince1970: file.startTimestamp)
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyy-MM-dd"
        let datePart = formatter.string(from: startDate)
        let shortUUID = String(file.sessionUUID.prefix(8))
        return documentsDirectory().appendingPathComponent("\(datePart)_\(shortUUID).json")
    }

    static func findFileURL(uuid: String) -> URL? {
        let suffix = "_\(uuid.prefix(8)).json"
        let dir = documentsDirectory()
        let entries = (try? FileManager.default.contentsOfDirectory(at: dir, includingPropertiesForKeys: nil)) ?? []
        if let newFormat = entries.first(where: { $0.lastPathComponent.hasSuffix(suffix) }) {
            return newFormat
        }
        let legacy = dir.appendingPathComponent("\(uuid).json")
        return FileManager.default.fileExists(atPath: legacy.path) ? legacy : nil
    }

    static func write(file: SessionFile) {
        let url = fileURL(for: file)
        do {
            let encoder = JSONEncoder()
            encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
            let data = try encoder.encode(file)
            try data.write(to: url, options: .atomic)
            logger.info("Wrote \(url.lastPathComponent) (\(data.count) bytes)")
        } catch {
            logger.error("Write failed for \(file.sessionUUID): \(error.localizedDescription)")
        }
    }

    static func loadFile(uuid: String) -> SessionFile? {
        guard let url = findFileURL(uuid: uuid) else { return nil }
        guard let data = try? Data(contentsOf: url) else { return nil }
        return try? JSONDecoder().decode(SessionFile.self, from: data)
    }

    static func mutateFile(uuid: String, _ change: (inout SessionFile) -> Void) {
        guard var file = loadFile(uuid: uuid) else {
            logger.error("Cannot mutate missing file \(uuid)")
            return
        }
        change(&file)
        write(file: file)
    }

    static func appendFollowupRating(_ rating: FollowupRating, to sessionUUID: String, at date: Date = Date()) {
        mutateFile(uuid: sessionUUID) { file in
            file.followupRating = rating
            file.followupRespondedAt = date.timeIntervalSince1970
        }
    }

    static func appendExperimentAudit(_ audit: ExperimentAudit, to sessionUUID: String) {
        mutateFile(uuid: sessionUUID) { file in
            file.experimentAudit = audit
        }
    }
}
