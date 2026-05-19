//
//  ContentView.swift
//  NapValidator Watch App
//
//  Created by Michael E Lanaux on 5/13/26.
//

import SwiftUI

struct ContentView: View {
    @State private var controller = SessionController()

    var body: some View {
        ScrollView {
            VStack(spacing: 10) {
                Text(controller.monitor.status.description)
                    .font(.caption2)
                    .foregroundStyle(statusColor)
                    .multilineTextAlignment(.center)

                VStack(spacing: 2) {
                    Text("Samples")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    Text("\(controller.monitor.sampleCount)")
                        .font(.title2.monospacedDigit())
                }

                VStack(spacing: 2) {
                    Text("Latest HR")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    if let bpm = controller.monitor.latestHeartRate {
                        Text("\(Int(bpm.rounded())) bpm")
                            .font(.title3.monospacedDigit())
                    } else {
                        Text("—")
                            .font(.title3)
                            .foregroundStyle(.secondary)
                    }
                }

                actionButton
            }
            .padding(.vertical, 8)
        }
        .sheet(isPresented: ratingSheetBinding) {
            WakeRatingSheet { rating in
                controller.submitWakeRating(rating)
            }
        }
        .task {
            await NotificationCoordinator.shared.requestAuthorizationIfNeeded()
        }
    }

    @ViewBuilder
    private var actionButton: some View {
        switch controller.phase {
        case .recording:
            Button("Stop session", role: .destructive) {
                controller.stop()
            }
        case .idle:
            Button("Start session") {
                Task { await controller.start() }
            }
            .disabled(!controller.canStart)
        case .starting, .stopping, .awaitingRating:
            ProgressView()
        }
    }

    private var ratingSheetBinding: Binding<Bool> {
        Binding(
            get: {
                if case .awaitingRating = controller.phase { return true }
                return false
            },
            set: { _ in }
        )
    }

    private var statusColor: Color {
        switch controller.monitor.status {
        case .running: return .green
        case .error: return .red
        case .authorizing, .stopping: return .yellow
        case .idle: return .secondary
        }
    }
}

private struct WakeRatingSheet: View {
    let onSelect: (SessionRecorder.WakeRating) -> Void

    var body: some View {
        ScrollView {
            VStack(spacing: 8) {
                Text("How do you feel?")
                    .font(.headline)
                    .padding(.top, 4)
                ForEach(SessionRecorder.WakeRating.allCases) { rating in
                    Button(rating.label) {
                        onSelect(rating)
                    }
                    .buttonStyle(.borderedProminent)
                    .frame(maxWidth: .infinity)
                }
            }
            .padding(.vertical, 8)
        }
        .interactiveDismissDisabled()
    }
}

#Preview {
    ContentView()
}
