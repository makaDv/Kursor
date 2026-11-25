import Foundation
import Security

/// Keychain-backed key/value store (refresh token).
///
/// Items are readable only after the first unlock, never leave this device
/// (no iCloud Keychain sync, not restored onto another phone from a backup).
final class SecureStore {
    private let service = "io.github.makadv.padlink.secure"

    private func baseQuery(_ key: String) -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: key
        ]
    }

    func get(_ key: String) -> String? {
        var query = baseQuery(key)
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var item: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
              let data = item as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    func set(_ key: String, _ value: String) -> Bool {
        let data = Data(value.utf8)
        let query = baseQuery(key)
        let attrs: [String: Any] = [
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        ]
        let status = SecItemUpdate(query as CFDictionary, attrs as CFDictionary)
        if status == errSecItemNotFound {
            var add = query
            attrs.forEach { add[$0.key] = $0.value }
            return SecItemAdd(add as CFDictionary, nil) == errSecSuccess
        }
        return status == errSecSuccess
    }

    func remove(_ key: String) {
        SecItemDelete(baseQuery(key) as CFDictionary)
    }
}
