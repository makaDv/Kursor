import UIKit
import Capacitor

class SceneDelegate: UIResponder, UIWindowSceneDelegate {
    var window: UIWindow?

    func scene(_ scene: UIScene, willConnectTo session: UISceneSession, options connectionOptions: UIScene.ConnectionOptions) {
        guard let windowScene = scene as? UIWindowScene else { return }

        window = UIWindow(windowScene: windowScene)
        window?.rootViewController = CAPBridgeViewController()
        window?.makeKeyAndVisible()

        SceneDelegateProxy.shared.scene(scene, willConnectTo: session, options: connectionOptions)

        // Launched from a home-screen quick action (Mouse / Tastiera / Schermo).
        if let item = connectionOptions.shortcutItem {
            storeLaunchTab(item)
        }
    }

    func windowScene(_ windowScene: UIWindowScene, performActionFor shortcutItem: UIApplicationShortcutItem,
                     completionHandler: @escaping (Bool) -> Void) {
        completionHandler(storeLaunchTab(shortcutItem))
    }

    /// Hands the requested tab to the PadLinkNative plugin (UserDefaults + notification, see Extras.swift).
    @discardableResult
    private func storeLaunchTab(_ item: UIApplicationShortcutItem) -> Bool {
        let prefix = "padlink.tab."
        guard item.type.hasPrefix(prefix) else { return false }
        UserDefaults.standard.set(String(item.type.dropFirst(prefix.count)), forKey: "padlink.launchTab")
        NotificationCenter.default.post(name: Notification.Name("PadLinkLaunchTab"), object: nil)
        return true
    }

    func scene(_ scene: UIScene, openURLContexts URLContexts: Set<UIOpenURLContext>) {
        SceneDelegateProxy.shared.scene(scene, openURLContexts: URLContexts)
    }

    func scene(_ scene: UIScene, continue userActivity: NSUserActivity) {
        SceneDelegateProxy.shared.scene(scene, continue: userActivity)
    }
}
