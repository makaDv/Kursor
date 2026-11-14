import Capacitor
import Foundation

/// Native bridge used by the Kursor app (see client/src/lib/native.ts).
///
/// All traffic to the PC goes through here instead of the WebView so the PC's
/// certificate can be pinned without installing any profile on the phone.
@objc(KursorNativePlugin)
public class KursorNativePlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "KursorNativePlugin"
    public let jsName = "KursorNative"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "secureGet", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "secureSet", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "secureRemove", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "request", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "probe", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "wsOpen", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "wsSend", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "wsClose", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "scanQr", returnType: CAPPluginReturnPromise)
    ]

    // Same value the server allow-lists for the bundled app (security/origin.py).
    private static let appOrigin = "https://localhost"
    private static let maxBody = 1024 * 1024

    private let store = SecureStore()
    private let lock = NSLock()
    private var sessions: [String: URLSession] = [:]
    private var sockets: [String: (task: URLSessionWebSocketTask, session: URLSession, pending: Int)] = [:]

    deinit {
        lock.lock()
        sockets.values.forEach { $0.task.cancel(with: .goingAway, reason: nil); $0.session.invalidateAndCancel() }
        lock.unlock()
    }

    // MARK: helpers

    private func validKey(_ call: CAPPluginCall) -> String? {
        guard let key = call.getString("key"), key.range(of: "^[a-z_]{1,32}$", options: .regularExpression) != nil else {
            call.reject("invalid key", "bad_request")
            return nil
        }
        return key
    }

    /// nil = system trust, .some(pin) = pinned. Rejects the call and returns false if malformed.
    private func readPin(_ call: CAPPluginCall) -> (ok: Bool, pin: String?) {
        guard let pin = call.getString("pin"), !pin.isEmpty else { return (true, nil) }
        guard pin.range(of: "^[A-Za-z0-9_-]{43}$", options: .regularExpression) != nil else {
            call.reject("invalid pin", "bad_request")
            return (false, nil)
        }
        return (true, pin)
    }

    private func session(for pin: String?) -> URLSession {
        let key = pin ?? "<system>"
        lock.lock()
        defer { lock.unlock() }
        if let s = sessions[key] { return s }
        let s = makeSession(PinnedSessionDelegate(mode: pin.map { .pinned($0) } ?? .system))
        sessions[key] = s
        return s
    }

    private func makeSession(_ delegate: PinnedSessionDelegate) -> URLSession {
        let cfg = URLSessionConfiguration.ephemeral
        cfg.timeoutIntervalForRequest = 30
        cfg.httpCookieAcceptPolicy = .never
        cfg.httpShouldSetCookies = false
        cfg.urlCache = nil
        cfg.tlsMinimumSupportedProtocolVersion = .TLSv12
        return URLSession(configuration: cfg, delegate: delegate, delegateQueue: nil)
    }

    private static func errorCode(_ error: Error, _ session: URLSession) -> String {
        if (session.delegate as? PinnedSessionDelegate)?.pinRejected == true { return "pin_mismatch" }
        let ns = error as NSError
        if ns.domain == NSURLErrorDomain,
           [NSURLErrorServerCertificateUntrusted, NSURLErrorSecureConnectionFailed,
            NSURLErrorServerCertificateHasBadDate, NSURLErrorCancelled].contains(ns.code) {
            return "tls"
        }
        return "network"
    }

    private func httpsURL(_ call: CAPPluginCall, scheme: String) -> URL? {
        guard let s = call.getString("url"), let url = URL(string: s), url.scheme?.lowercased() == scheme,
              url.host != nil else {
            call.reject("\(scheme) only", "bad_request")
            return nil
        }
        return url
    }

    // MARK: secure storage

    @objc func secureGet(_ call: CAPPluginCall) {
        guard let key = validKey(call) else { return }
        call.resolve(["value": orNull(store.get(key))])
    }

    @objc func secureSet(_ call: CAPPluginCall) {
        guard let key = validKey(call) else { return }
        guard let value = call.getString("value"), value.count <= 4096 else {
            call.reject("invalid value", "bad_request")
            return
        }
        store.set(key, value) ? call.resolve() : call.reject("keychain failed", "storage")
    }

    @objc func secureRemove(_ call: CAPPluginCall) {
        guard let key = validKey(call) else { return }
        store.remove(key)
        call.resolve()
    }

    // MARK: HTTPS

    @objc func request(_ call: CAPPluginCall) {
        guard let url = httpsURL(call, scheme: "https") else { return }
        let (ok, pin) = readPin(call)
        guard ok else { return }
        var req = URLRequest(url: url)
        req.httpMethod = (call.getString("method") ?? "GET").uppercased()
        req.cachePolicy = .reloadIgnoringLocalCacheData
        req.setValue(Self.appOrigin, forHTTPHeaderField: "Origin")
        for (name, value) in call.getObject("headers") ?? [:] {
            if let v = value as? String { req.setValue(v, forHTTPHeaderField: name) }
        }
        if let body = call.getString("body") { req.httpBody = Data(body.utf8) }

        let session = self.session(for: pin)
        session.dataTask(with: req) { data, response, error in
            if let error = error {
                call.reject(error.localizedDescription, Self.errorCode(error, session))
                return
            }
            guard let http = response as? HTTPURLResponse else {
                call.reject("no response", "network")
                return
            }
            let bytes = data ?? Data()
            guard bytes.count <= Self.maxBody else {
                call.reject("response too large", "network")
                return
            }
            var headers: [String: String] = [:]
            for (k, v) in http.allHeaderFields {
                if let k = k as? String { headers[k.lowercased()] = "\(v)" }
            }
            call.resolve([
                "status": http.statusCode,
                "headers": headers,
                "body": String(data: bytes, encoding: .utf8) ?? ""
            ])
        }.resume()
    }

    @objc func probe(_ call: CAPPluginCall) {
        guard let base = httpsURL(call, scheme: "https") else { return }
        let delegate = PinnedSessionDelegate(mode: .probe)
        let session = makeSession(delegate)
        var req = URLRequest(url: base.appendingPathComponent("api/health"))
        req.timeoutInterval = 8
        session.dataTask(with: req) { _, _, error in
            defer { session.finishTasksAndInvalidate() }
            if let error = error, delegate.probedFingerprint == nil {
                call.reject(error.localizedDescription, Self.errorCode(error, session))
                return
            }
            call.resolve([
                "fingerprint": orNull(delegate.probedFingerprint),
                "publiclyTrusted": delegate.publiclyTrusted
            ])
        }.resume()
    }

    // MARK: WebSocket

    private func emit(_ id: String, _ type: String, _ extra: [String: Any] = [:]) {
        var ev = extra
        ev["id"] = id
        ev["type"] = type
        notifyListeners("ws", data: ev)
    }

    private func removeSocket(_ id: String) -> Bool {
        lock.lock()
        defer { lock.unlock() }
        guard let s = sockets.removeValue(forKey: id) else { return false }
        s.session.finishTasksAndInvalidate()
        return true
    }

    @objc func wsOpen(_ call: CAPPluginCall) {
        guard let url = httpsURL(call, scheme: "wss") else { return }
        let (ok, pin) = readPin(call)
        guard ok else { return }
        let id = UUID().uuidString
        let delegate = PinnedSessionDelegate(mode: pin.map { .pinned($0) } ?? .system)
        delegate.onOpen = { [weak self] _ in self?.emit(id, "open") }
        delegate.onClose = { [weak self] _, code, reason in
            guard let self = self, self.removeSocket(id) else { return }
            self.emit(id, "close", ["code": code, "reason": reason ?? ""])
        }
        let session = makeSession(delegate)
        var req = URLRequest(url: url)
        req.setValue(Self.appOrigin, forHTTPHeaderField: "Origin")
        let task = session.webSocketTask(with: req)
        task.maximumMessageSize = 8 * 1024 * 1024
        lock.lock()
        sockets[id] = (task, session, 0)
        lock.unlock()
        receive(id, task)
        task.resume()
        call.resolve(["id": id])
    }

    private func receive(_ id: String, _ task: URLSessionWebSocketTask) {
        task.receive { [weak self] result in
            guard let self = self else { return }
            switch result {
            case .success(.string(let text)):
                self.emit(id, "text", ["data": text])
            case .success(.data(let data)):
                self.emit(id, "binary", ["data": data.base64EncodedString()])
            case .success:
                break
            case .failure:
                return // close is reported by the delegate
            }
            self.receive(id, task)
        }
    }

    @objc func wsSend(_ call: CAPPluginCall) {
        let id = call.getString("id") ?? ""
        lock.lock()
        let entry = sockets[id]
        if entry != nil { sockets[id]?.pending += 1 }
        let pending = sockets[id]?.pending ?? 0
        lock.unlock()
        guard let task = entry?.task, let data = call.getString("data") else {
            call.resolve(["ok": false, "buffered": 0])
            return
        }
        task.send(.string(data)) { [weak self] _ in
            guard let self = self else { return }
            self.lock.lock()
            if self.sockets[id] != nil { self.sockets[id]?.pending -= 1 }
            self.lock.unlock()
        }
        call.resolve(["ok": true, "buffered": pending])
    }

    @objc func wsClose(_ call: CAPPluginCall) {
        let id = call.getString("id") ?? ""
        lock.lock()
        let task = sockets[id]?.task
        lock.unlock()
        let code = URLSessionWebSocketTask.CloseCode(rawValue: call.getInt("code") ?? 1000) ?? .normalClosure
        task?.cancel(with: code, reason: nil)
        call.resolve()
    }

    // MARK: QR scanner

    @objc func scanQr(_ call: CAPPluginCall) {
        DispatchQueue.main.async { [weak self] in
            guard let presenter = self?.bridge?.viewController else {
                call.reject("no view controller", "unavailable")
                return
            }
            let scanner = QrScannerViewController { value in
                call.resolve(["value": orNull(value)])
            }
            scanner.modalPresentationStyle = .fullScreen
            presenter.present(scanner, animated: true)
        }
    }
}

/// JSON null for absent values (an Optional boxed in Any does not serialise).
private func orNull(_ value: String?) -> Any {
    value ?? NSNull()
}
