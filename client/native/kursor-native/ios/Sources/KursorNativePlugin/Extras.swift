import Foundation
import LocalAuthentication
import Network
import StoreKit
import UIKit

/// Bonjour discovery of `_padlink._tcp` (no extra entitlement; needs NSBonjourServices
/// and the local-network permission already declared in Info.plist).
final class PadLinkBrowser {
    struct Found {
        let host: String
        let port: Int
        let fp: String?
        let name: String?
    }

    private var browser: NWBrowser?
    private var connections: [NWConnection] = []
    private var found: [Found] = []
    private let queue = DispatchQueue(label: "padlink.discovery")

    func discover(timeout: TimeInterval, completion: @escaping ([Found]) -> Void) {
        let params = NWParameters()
        params.includePeerToPeer = false
        let browser = NWBrowser(for: .bonjourWithTXTRecord(type: "_padlink._tcp", domain: nil), using: params)
        self.browser = browser
        browser.browseResultsChangedHandler = { [weak self] results, _ in
            guard let self = self else { return }
            for result in results {
                var fp: String?
                var name: String?
                if case let .bonjour(txt) = result.metadata {
                    fp = txt["fp"]
                    name = txt["name"]
                }
                self.resolve(result.endpoint, fp: fp, name: name)
            }
        }
        browser.start(queue: queue)
        queue.asyncAfter(deadline: .now() + timeout) { [weak self] in
            guard let self = self else { return }
            browser.cancel()
            self.connections.forEach { $0.cancel() }
            self.connections.removeAll()
            let result = self.found
            DispatchQueue.main.async { completion(result) }
        }
    }

    /// Resolve the service endpoint to an IPv4 address by opening (and closing) a TCP connection.
    private func resolve(_ endpoint: NWEndpoint, fp: String?, name: String?) {
        let params = NWParameters.tcp
        if let ip = params.defaultProtocolStack.internetProtocol as? NWProtocolIP.Options {
            ip.version = .v4
        }
        let conn = NWConnection(to: endpoint, using: params)
        connections.append(conn)
        conn.stateUpdateHandler = { [weak self, weak conn] state in
            guard let self = self, let conn = conn else { return }
            if case .ready = state,
               case let .hostPort(host, port)? = conn.currentPath?.remoteEndpoint {
                var h = "\(host)"
                if let pct = h.firstIndex(of: "%") { h = String(h[..<pct]) }
                if !self.found.contains(where: { $0.host == h && $0.port == Int(port.rawValue) }) {
                    self.found.append(Found(host: h, port: Int(port.rawValue), fp: fp, name: name))
                }
                conn.cancel()
            } else if case .failed = state {
                conn.cancel()
            }
        }
        conn.start(queue: queue)
    }
}

enum Biometrics {
    static func available() -> Bool {
        LAContext().canEvaluatePolicy(.deviceOwnerAuthentication, error: nil)
    }

    static func authenticate(reason: String, completion: @escaping (Bool, String?) -> Void) {
        let ctx = LAContext()
        ctx.evaluatePolicy(.deviceOwnerAuthentication, localizedReason: reason) { ok, error in
            DispatchQueue.main.async { completion(ok, error?.localizedDescription) }
        }
    }
}

enum Review {
    static func request() {
        DispatchQueue.main.async {
            let scene = UIApplication.shared.connectedScenes
                .first { $0.activationState == .foregroundActive } as? UIWindowScene
            if let scene = scene {
                SKStoreReviewController.requestReview(in: scene)
            }
        }
    }
}

/// Home-screen quick actions are received by SceneDelegate (app target), which stores the
/// requested tab here via UserDefaults + a notification, so the plugin needs no import.
enum LaunchTab {
    static let defaultsKey = "padlink.launchTab"
    static let notification = Notification.Name("PadLinkLaunchTab")

    static func take() -> String? {
        let tab = UserDefaults.standard.string(forKey: defaultsKey)
        UserDefaults.standard.removeObject(forKey: defaultsKey)
        return tab
    }
}
