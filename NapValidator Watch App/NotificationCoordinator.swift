//
//  NotificationCoordinator.swift
//  NapValidator Watch App
//
//  Owns notification authorization, the 4-action follow-up category,
//  scheduling the 3-hour post-wake prompt, and routing the user's
//  response back onto the matching session JSON.
//

import Foundation
import UserNotifications
import OSLog

@MainActor
final class NotificationCoordinator: NSObject {
    static let shared = NotificationCoordinator()
    nonisolated static let logger = Logger(subsystem: "com.elanaux.NapValidator", category: "Notifications")

    nonisolated static let followupCategoryID = "FOLLOWUP_RATING"
    nonisolated static let sessionUUIDKey = "sessionUUID"

    nonisolated static let debugFollowupDelayOverride: TimeInterval? = 3 * 60 * 60

    nonisolated static let defaultFollowupDelay: TimeInterval = {
        #if DEBUG
        return debugFollowupDelayOverride ?? 60
        #else
        return 3 * 60 * 60
        #endif
    }()

    nonisolated private static let actionMap: [(id: String, rating: SessionRecorder.FollowupRating)] = [
        ("FOLLOWUP_STILL_FOCUSED", .stillFocused),
        ("FOLLOWUP_WEARING_OFF", .wearingOff),
        ("FOLLOWUP_ALREADY_WORN_OFF", .alreadyWornOff),
        ("FOLLOWUP_CRASHED", .crashed),
    ]

    private override init() { super.init() }

    func bootstrap() {
        let center = UNUserNotificationCenter.current()
        center.delegate = self
        registerCategory()
        Self.logNotificationSettings(reason: "bootstrap")
    }

    func requestAuthorizationIfNeeded() async {
        let center = UNUserNotificationCenter.current()
        let settings = await center.notificationSettings()
        Self.logger.info("Auth check: status=\(Self.describe(settings.authorizationStatus)) alert=\(Self.describe(settings.alertSetting))")
        guard settings.authorizationStatus == .notDetermined else { return }
        do {
            let granted = try await center.requestAuthorization(options: [.alert, .sound])
            Self.logger.info("Notification auth granted=\(granted)")
            Self.logNotificationSettings(reason: "post-request")
        } catch {
            Self.logger.error("Notification auth failed: \(error.localizedDescription)")
        }
    }

    func scheduleFollowup(sessionUUID: String, delay: TimeInterval = NotificationCoordinator.defaultFollowupDelay) {
        let content = UNMutableNotificationContent()
        content.title = "Nap check-in"
        content.body = "When did the boost wear off?"
        content.categoryIdentifier = Self.followupCategoryID
        content.userInfo = [Self.sessionUUIDKey: sessionUUID]

        let trigger = UNTimeIntervalNotificationTrigger(timeInterval: delay, repeats: false)
        let request = UNNotificationRequest(identifier: "followup-\(sessionUUID)",
                                            content: content, trigger: trigger)
        UNUserNotificationCenter.current().add(request) { error in
            if let error {
                Self.logger.error("Schedule failed: \(error.localizedDescription)")
            } else {
                Self.logger.info("Scheduled followup for \(sessionUUID) in \(delay)s")
                Self.logPendingFollowups(reason: "post-schedule")
            }
        }
    }

    nonisolated private static func logNotificationSettings(reason: String) {
        UNUserNotificationCenter.current().getNotificationSettings { settings in
            logger.info("Settings (\(reason)): status=\(describe(settings.authorizationStatus)) alert=\(describe(settings.alertSetting)) sound=\(describe(settings.soundSetting)) notificationCenter=\(describe(settings.notificationCenterSetting))")
        }
    }

    nonisolated private static func logPendingFollowups(reason: String) {
        UNUserNotificationCenter.current().getPendingNotificationRequests { requests in
            let ours = requests.filter { $0.identifier.hasPrefix("followup-") }
            logger.info("Pending (\(reason)): count=\(ours.count)")
            for req in ours {
                if let trig = req.trigger as? UNTimeIntervalNotificationTrigger {
                    logger.info("  id=\(req.identifier) firesIn=\(trig.timeInterval)s category=\(req.content.categoryIdentifier)")
                } else {
                    logger.info("  id=\(req.identifier) trigger=\(String(describing: req.trigger))")
                }
            }
        }
    }

    nonisolated private static func describe(_ status: UNAuthorizationStatus) -> String {
        switch status {
        case .notDetermined: return "notDetermined"
        case .denied: return "denied"
        case .authorized: return "authorized"
        case .provisional: return "provisional"
        case .ephemeral: return "ephemeral"
        @unknown default: return "unknown(\(status.rawValue))"
        }
    }

    nonisolated private static func describe(_ setting: UNNotificationSetting) -> String {
        switch setting {
        case .notSupported: return "notSupported"
        case .disabled: return "disabled"
        case .enabled: return "enabled"
        @unknown default: return "unknown(\(setting.rawValue))"
        }
    }

    private func registerCategory() {
        let actions = Self.actionMap.map { entry in
            UNNotificationAction(identifier: entry.id,
                                 title: entry.rating.label,
                                 options: [.foreground])
        }
        let category = UNNotificationCategory(identifier: Self.followupCategoryID,
                                              actions: actions,
                                              intentIdentifiers: [],
                                              options: [])
        UNUserNotificationCenter.current().setNotificationCategories([category])
    }

    nonisolated fileprivate static func rating(for actionIdentifier: String) -> SessionRecorder.FollowupRating? {
        actionMap.first(where: { $0.id == actionIdentifier })?.rating
    }
}

extension NotificationCoordinator: UNUserNotificationCenterDelegate {
    nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter,
                                            willPresent notification: UNNotification,
                                            withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void) {
        completionHandler([.banner, .sound])
    }

    nonisolated func userNotificationCenter(_ center: UNUserNotificationCenter,
                                            didReceive response: UNNotificationResponse,
                                            withCompletionHandler completionHandler: @escaping () -> Void) {
        let actionID = response.actionIdentifier
        let userInfo = response.notification.request.content.userInfo
        let sessionUUID = userInfo[Self.sessionUUIDKey] as? String

        if let sessionUUID, let rating = Self.rating(for: actionID) {
            Self.logger.info("Followup response \(rating.rawValue) for \(sessionUUID)")
            Task { @MainActor in
                SessionRecorder.appendFollowupRating(rating, to: sessionUUID)
            }
        } else {
            Self.logger.info("Followup dismissed or unrecognized action=\(actionID)")
        }
        completionHandler()
    }
}
