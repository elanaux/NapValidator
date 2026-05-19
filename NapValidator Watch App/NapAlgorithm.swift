//
//  NapAlgorithm.swift
//  NapValidator Watch App
//
//  Three-phase wake-trigger state machine (settling → asleep → confirming → wakeFired).
//  Currently runs in observe-only mode: all phases evaluated and logged, but the
//  wakeFired transition has no user-facing side effect. Flip `observeOnly` to false
//  in a future change to activate the wake action.
//

import Foundation
import OSLog

let observeOnly = true
private let observeOnlyFlag: Bool = observeOnly  // alias to dodge name-shadowing inside Parameters.current

@MainActor
@Observable
final class NapAlgorithm {
    static let logger = Logger(subsystem: "com.elanaux.NapValidator", category: "NapAlgorithm")

    enum Phase: String {
        case settling, asleep, confirming
        case wakeFired = "wake_fired"
    }

    struct Decision: Codable {
        let t: TimeInterval
        let phase_from: String
        let phase_to: String
        let reason: String
        var awake_reference_hr: Double?
        var light_ref_hr: Double?
        var light_ref_sd: Double?
        var current_avg_hr: Double?
        var current_sd: Double?

        func encode(to encoder: Encoder) throws {
            var c = encoder.container(keyedBy: CodingKeys.self)
            try c.encode(t, forKey: .t)
            try c.encode(phase_from, forKey: .phase_from)
            try c.encode(phase_to, forKey: .phase_to)
            try c.encode(reason, forKey: .reason)
            try c.encodeIfPresent(awake_reference_hr, forKey: .awake_reference_hr)
            try c.encodeIfPresent(light_ref_hr, forKey: .light_ref_hr)
            try c.encodeIfPresent(light_ref_sd, forKey: .light_ref_sd)
            try c.encodeIfPresent(current_avg_hr, forKey: .current_avg_hr)
            try c.encodeIfPresent(current_sd, forKey: .current_sd)
        }
    }

    struct Parameters: Codable {
        let version: String
        let settling_to_asleep_hr_drop: Double
        let settling_to_asleep_sustain_s: Int
        let awake_reference_window_s: Int
        let light_reference_window_s: Int
        let motion_threshold_rms: Double
        let n_avg_s: Int
        let n_var_s: Int
        let t_hr: Double
        let t_var: Double
        let d_sustain_s: Int
        let d_confirm_s: Int
        let observeOnly: Bool

        // v0.1.2: adds Phase 1 motion-stall decision logging (phase1_motion_unavailable / phase1_motion_resumed)
        static let current = Parameters(
            version: "0.1.2",
            settling_to_asleep_hr_drop: 2.0,
            settling_to_asleep_sustain_s: 90,
            awake_reference_window_s: 180,
            light_reference_window_s: 180,
            motion_threshold_rms: 0.005,
            n_avg_s: 60,
            n_var_s: 60,
            t_hr: 5.0,
            t_var: 0.8,
            d_sustain_s: 60,
            d_confirm_s: 30,
            observeOnly: observeOnlyFlag
        )
    }

    private let awakeReferenceWindowSec: TimeInterval = 180
    private let settlingSustainSec: TimeInterval = 90
    private let settlingHRDrop: Double = 2.0
    private let settlingMotionRMSMax: Double = 0.005
    private let lightReferenceWindowSec: TimeInterval = 180
    private let deepeningWindowSec: TimeInterval = 60
    private let deepeningHRDrop: Double = 5.0
    private let deepeningSDMax: Double = 0.8
    private let deepeningSustainSec: TimeInterval = 60
    private let confirmingSustainSec: TimeInterval = 30

    private(set) var phase: Phase = .settling
    private(set) var decisions: [Decision] = []
    var onDecision: ((Decision) -> Void)?

    private var hrSamples: [(t: TimeInterval, bpm: Double)] = []
    private var motionMagnitudes: [(t: TimeInterval, m: Double)] = []

    private var sessionStart: TimeInterval = 0
    private var awakeReferenceHR: Double?
    private var onsetTime: TimeInterval?
    private var lightRefHR: Double?
    private var lightRefSD: Double?
    private var deepeningHoldSince: TimeInterval?
    private var confirmingStart: TimeInterval?
    private var stopped = false
    private var phase1MotionUnavailableLogged = false

    func start(at date: Date) {
        sessionStart = date.timeIntervalSince1970
        phase = .settling
        decisions.removeAll()
        hrSamples.removeAll()
        motionMagnitudes.removeAll()
        awakeReferenceHR = nil
        onsetTime = nil
        lightRefHR = nil
        lightRefSD = nil
        deepeningHoldSince = nil
        confirmingStart = nil
        stopped = false
        phase1MotionUnavailableLogged = false
        Self.logger.info("NapAlgorithm started t=\(self.sessionStart) observeOnly=\(observeOnly)")
    }

    func stop() {
        stopped = true
        Self.logger.info("NapAlgorithm stopped in phase=\(self.phase.rawValue) decisions=\(self.decisions.count)")
    }

    nonisolated func ingestHR(bpm: Double, at date: Date) {
        let t = date.timeIntervalSince1970
        Task { @MainActor [weak self] in
            guard let self else { return }
            guard !self.stopped, self.phase != .wakeFired else { return }
            self.hrSamples.append((t, bpm))
            self.evictOldHR(now: t)
            self.evaluate(now: t)
        }
    }

    nonisolated func ingestMotion(magnitude: Double, at date: Date) {
        let t = date.timeIntervalSince1970
        Task { @MainActor [weak self] in
            guard let self else { return }
            guard !self.stopped, self.phase != .wakeFired else { return }
            self.motionMagnitudes.append((t, magnitude))
        }
    }

    private func evictOldHR(now: TimeInterval) {
        let cutoff = now - awakeReferenceWindowSec
        if let firstFresh = hrSamples.firstIndex(where: { $0.t >= cutoff }), firstFresh > 0 {
            hrSamples.removeFirst(firstFresh)
        }
    }

    private func evaluate(now: TimeInterval) {
        switch phase {
        case .settling:
            evaluateSettling(now: now)
        case .asleep:
            if lightRefHR == nil {
                evaluateLightReference(now: now)
            } else {
                evaluateDeepening(now: now)
            }
        case .confirming:
            evaluateConfirming(now: now)
        case .wakeFired:
            break
        }
    }

    private func evaluateSettling(now: TimeInterval) {
        guard (now - sessionStart) >= awakeReferenceWindowSec else { return }

        if awakeReferenceHR == nil {
            let refWindow = hrSamples.filter { ($0.t - sessionStart) <= awakeReferenceWindowSec }
            guard !refWindow.isEmpty else { return }
            awakeReferenceHR = median(refWindow.map { $0.bpm })
        }
        guard let awakeRef = awakeReferenceHR else { return }

        let hrWindow = hrSamples.filter { (now - $0.t) <= settlingSustainSec }
        guard !hrWindow.isEmpty else { return }
        let avgHR = mean(hrWindow.map { $0.bpm })

        let motionWindow = motionMagnitudes.filter { (now - $0.t) <= settlingSustainSec }
        guard !motionWindow.isEmpty else {
            if !phase1MotionUnavailableLogged {
                phase1MotionUnavailableLogged = true
                log(Decision(t: now, phase_from: "settling", phase_to: "settling", reason: "phase1_motion_unavailable"))
            }
            return
        }
        if phase1MotionUnavailableLogged {
            phase1MotionUnavailableLogged = false
            log(Decision(t: now, phase_from: "settling", phase_to: "settling", reason: "phase1_motion_resumed"))
        }
        let motionRMS = rms(motionWindow.map { $0.m })

        let hrCondition = avgHR <= (awakeRef - settlingHRDrop)
        let motionCondition = motionRMS < settlingMotionRMSMax

        if hrCondition && motionCondition {
            onsetTime = now
            phase = .asleep
            var d = Decision(t: now, phase_from: "settling", phase_to: "asleep", reason: "onset_detected")
            d.awake_reference_hr = awakeRef
            log(d)
        }
    }

    private func evaluateLightReference(now: TimeInterval) {
        guard let onset = onsetTime else { return }
        guard (now - onset) >= lightReferenceWindowSec else { return }

        let refWindow = hrSamples.filter { $0.t >= onset && $0.t <= (onset + lightReferenceWindowSec) }
        guard !refWindow.isEmpty else { return }

        let values = refWindow.map { $0.bpm }
        let hr = median(values)
        let sd = stddev(values)

        lightRefHR = hr
        lightRefSD = sd

        var d = Decision(t: now, phase_from: "asleep", phase_to: "asleep", reason: "light_reference_captured")
        d.light_ref_hr = hr
        d.light_ref_sd = sd
        log(d)
    }

    private func evaluateDeepening(now: TimeInterval) {
        guard let lightHR = lightRefHR else { return }

        let window = hrSamples.filter { (now - $0.t) <= deepeningWindowSec }
        guard !window.isEmpty else { return }

        let values = window.map { $0.bpm }
        let avg = mean(values)
        let sd = stddev(values)

        let condition = (avg <= (lightHR - deepeningHRDrop)) && (sd <= deepeningSDMax)

        if condition {
            if deepeningHoldSince == nil {
                deepeningHoldSince = now
            } else if let holdStart = deepeningHoldSince, (now - holdStart) >= deepeningSustainSec {
                phase = .confirming
                confirmingStart = now
                var d = Decision(t: now, phase_from: "asleep", phase_to: "confirming", reason: "deepening_pattern_sustained")
                d.current_avg_hr = avg
                d.current_sd = sd
                log(d)
            }
        } else {
            deepeningHoldSince = nil
        }
    }

    private func evaluateConfirming(now: TimeInterval) {
        guard let lightHR = lightRefHR, let confirmStart = confirmingStart else { return }

        let window = hrSamples.filter { (now - $0.t) <= deepeningWindowSec }
        guard !window.isEmpty else { return }

        let values = window.map { $0.bpm }
        let avg = mean(values)
        let sd = stddev(values)

        let condition = (avg <= (lightHR - deepeningHRDrop)) && (sd <= deepeningSDMax)

        if !condition {
            phase = .asleep
            deepeningHoldSince = nil
            confirmingStart = nil
            var d = Decision(t: now, phase_from: "confirming", phase_to: "asleep", reason: "confirmation_failed")
            d.current_avg_hr = avg
            d.current_sd = sd
            log(d)
            return
        }

        if (now - confirmStart) >= confirmingSustainSec {
            phase = .wakeFired
            let reason = observeOnly ? "wake_fired_observe_only" : "wake_fired"
            var d = Decision(t: now, phase_from: "confirming", phase_to: "wake_fired", reason: reason)
            d.current_avg_hr = avg
            d.current_sd = sd
            log(d)
            // observeOnly: no user-facing wake action. Future change will gate a wake side effect here.
        }
    }

    private func log(_ d: Decision) {
        decisions.append(d)
        Self.logger.info("\(d.phase_from) -> \(d.phase_to) reason=\(d.reason) awakeRef=\(d.awake_reference_hr ?? -1) lightRef=\(d.light_ref_hr ?? -1) lightSD=\(d.light_ref_sd ?? -1) curAvg=\(d.current_avg_hr ?? -1) curSD=\(d.current_sd ?? -1)")
        onDecision?(d)
    }

    private func mean(_ xs: [Double]) -> Double {
        guard !xs.isEmpty else { return 0 }
        return xs.reduce(0, +) / Double(xs.count)
    }

    private func median(_ xs: [Double]) -> Double {
        guard !xs.isEmpty else { return 0 }
        let sorted = xs.sorted()
        let n = sorted.count
        if n % 2 == 1 { return sorted[n / 2] }
        return (sorted[n / 2 - 1] + sorted[n / 2]) / 2
    }

    private func stddev(_ xs: [Double]) -> Double {
        guard xs.count > 1 else { return 0 }
        let m = mean(xs)
        let variance = xs.reduce(0) { $0 + ($1 - m) * ($1 - m) } / Double(xs.count - 1)
        return variance.squareRoot()
    }

    private func rms(_ xs: [Double]) -> Double {
        guard !xs.isEmpty else { return 0 }
        let sumSquares = xs.reduce(0) { $0 + $1 * $1 }
        return (sumSquares / Double(xs.count)).squareRoot()
    }
}
