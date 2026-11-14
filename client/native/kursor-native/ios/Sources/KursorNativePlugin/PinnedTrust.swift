import CryptoKit
import Foundation
import Security

/// TLS trust for connections to the user's PC.
///
/// With a pin (SHA-256 of the PC's local CA certificate, delivered by the pairing
/// QR code or confirmed by the user through the verification code) the chain is
/// evaluated with that CA as the ONLY anchor: system and user-installed roots are
/// ignored, hostname (SAN) checking stays on. Without a pin (public certificate,
/// e.g. a Cloudflare tunnel) the default system evaluation is used.
enum PinnedTrust {
    static func fingerprint(_ cert: SecCertificate) -> String {
        let der = SecCertificateCopyData(cert) as Data
        return Data(SHA256.hash(data: der)).base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }

    static func chain(_ trust: SecTrust) -> [SecCertificate] {
        (SecTrustCopyCertificateChain(trust) as? [SecCertificate]) ?? []
    }

    /// Self-signed CA at the root of the presented chain.
    static func root(_ trust: SecTrust) -> SecCertificate? {
        // Evaluate once (result ignored) so the chain includes the server-sent CA.
        _ = SecTrustEvaluateWithError(trust, nil)
        return chain(trust).last
    }

    static func evaluate(_ trust: SecTrust, host: String, pin: String) -> Bool {
        _ = SecTrustEvaluateWithError(trust, nil)
        guard let anchor = chain(trust).first(where: { constantTimeEquals(fingerprint($0), pin) }) else {
            return false
        }
        // The pinned CA is private to this PC: it is the identity, so the hostname is not checked
        // (lets the app follow the PC to a new DHCP address found via Bonjour).
        SecTrustSetPolicies(trust, SecPolicyCreateSSL(true, nil))
        SecTrustSetAnchorCertificates(trust, [anchor] as CFArray)
        SecTrustSetAnchorCertificatesOnly(trust, true)
        return SecTrustEvaluateWithError(trust, nil)
    }

    private static func constantTimeEquals(_ a: String, _ b: String) -> Bool {
        let x = Array(a.utf8), y = Array(b.utf8)
        guard x.count == y.count else { return false }
        var diff: UInt8 = 0
        for i in 0..<x.count { diff |= x[i] ^ y[i] }
        return diff == 0
    }
}

/// URLSession delegate applying `PinnedTrust` and forwarding WebSocket lifecycle events.
final class PinnedSessionDelegate: NSObject, URLSessionWebSocketDelegate {
    enum Mode { case system, pinned(String), probe }

    let mode: Mode
    /// Probe results.
    private(set) var probedFingerprint: String?
    private(set) var publiclyTrusted = false
    /// Last TLS failure was a pin mismatch.
    private(set) var pinRejected = false

    var onOpen: ((URLSessionWebSocketTask) -> Void)?
    var onClose: ((URLSessionTask, Int, String?) -> Void)?

    init(mode: Mode) {
        self.mode = mode
    }

    func urlSession(_ session: URLSession, didReceive challenge: URLAuthenticationChallenge,
                    completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void) {
        handle(challenge, completionHandler)
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didReceive challenge: URLAuthenticationChallenge,
                    completionHandler: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void) {
        handle(challenge, completionHandler)
    }

    private func handle(_ challenge: URLAuthenticationChallenge,
                        _ completion: @escaping (URLSession.AuthChallengeDisposition, URLCredential?) -> Void) {
        guard challenge.protectionSpace.authenticationMethod == NSURLAuthenticationMethodServerTrust,
              let trust = challenge.protectionSpace.serverTrust else {
            completion(.cancelAuthenticationChallenge, nil)
            return
        }
        switch mode {
        case .system:
            completion(.performDefaultHandling, nil)
        case .pinned(let pin):
            if PinnedTrust.evaluate(trust, host: challenge.protectionSpace.host, pin: pin) {
                completion(.useCredential, URLCredential(trust: trust))
            } else {
                pinRejected = true
                completion(.cancelAuthenticationChallenge, nil)
            }
        case .probe:
            publiclyTrusted = SecTrustEvaluateWithError(trust, nil)
            if let root = PinnedTrust.root(trust) {
                probedFingerprint = PinnedTrust.fingerprint(root)
            }
            // Accept only so the single GET /api/health completes; nothing else is sent.
            completion(.useCredential, URLCredential(trust: trust))
        }
    }

    func urlSession(_ session: URLSession, webSocketTask: URLSessionWebSocketTask,
                    didOpenWithProtocol protocol: String?) {
        onOpen?(webSocketTask)
    }

    func urlSession(_ session: URLSession, webSocketTask: URLSessionWebSocketTask,
                    didCloseWith closeCode: URLSessionWebSocketTask.CloseCode, reason: Data?) {
        onClose?(webSocketTask, closeCode.rawValue, reason.flatMap { String(data: $0, encoding: .utf8) })
    }

    func urlSession(_ session: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        if task is URLSessionWebSocketTask {
            onClose?(task, 1006, pinRejected ? "pin_mismatch" : (error == nil ? nil : "network"))
        }
    }
}
