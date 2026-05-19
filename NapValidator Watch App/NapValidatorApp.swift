//
//  NapValidatorApp.swift
//  NapValidator Watch App
//
//  Created by Michael E Lanaux on 5/13/26.
//

import SwiftUI

@main
struct NapValidator_Watch_AppApp: App {
    init() {
        NotificationCoordinator.shared.bootstrap()
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
        }
    }
}
