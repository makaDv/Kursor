/**
 * Typed binding of the KursorNative plugin (client/native/kursor-native).
 * Android: OkHttp + Android Keystore + ZXing. iOS: URLSession + Keychain + AVFoundation.
 */
import { registerPlugin, type PluginListenerHandle } from '@capacitor/core'

export interface NativeResponse {
  status: number
  headers: Record<string, string>
  body: string
}

export type NativeWsEvent =
  | { id: string; type: 'open' }
  | { id: string; type: 'text'; data: string }
  | { id: string; type: 'binary'; data: string } // base64
  | { id: string; type: 'close'; code: number; reason?: string }

export interface KursorNativePlugin {
  secureGet(o: { key: string }): Promise<{ value: string | null }>
  secureSet(o: { key: string; value: string }): Promise<void>
  secureRemove(o: { key: string }): Promise<void>

  /** HTTPS request; with `pin` the PC's CA is the only trust anchor. Rejects with code pin_mismatch | tls | network. */
  request(o: {
    url: string
    method: string
    headers?: Record<string, string>
    body?: string
    pin?: string
  }): Promise<NativeResponse>

  /** One untrusted GET /api/health to read the PC's CA fingerprint (manual pairing). */
  probe(o: { url: string }): Promise<{ fingerprint: string | null; publiclyTrusted: boolean }>

  wsOpen(o: { url: string; pin?: string }): Promise<{ id: string }>
  wsSend(o: { id: string; data: string }): Promise<{ ok: boolean; buffered: number }>
  wsClose(o: { id: string; code?: number; reason?: string }): Promise<void>

  scanQr(): Promise<{ value: string | null }>

  /** Fingerprint / face / device PIN (Android BiometricPrompt, iOS LocalAuthentication). */
  biometricAvailable(): Promise<{ available: boolean }>
  biometricAuth(o: { reason: string }): Promise<{ ok: boolean; error?: string }>

  /** mDNS browse for PadLink PCs on the LAN (_padlink._tcp). */
  discover(o: { timeout?: number }): Promise<{ pcs: { host: string; port: number; fp: string | null; name: string | null }[] }>

  /** Wake-on-LAN magic packet (Android only; iOS rejects with code "unsupported"). */
  wakeOnLan(o: { mac: string }): Promise<void>

  /** Native store rating dialog (Play In-App Review / SKStoreReviewController). */
  requestReview(): Promise<void>

  /** Android: hardware volume keys emit "volumeKey" instead of changing the phone volume. */
  setVolumeKeyCapture(o: { enabled: boolean }): Promise<void>

  /** Tab requested by a launcher shortcut / quick action, if the app was opened from one. */
  getLaunchTab(): Promise<{ tab: string | null }>

  addListener(event: 'ws', fn: (ev: NativeWsEvent) => void): Promise<PluginListenerHandle>
  addListener(event: 'volumeKey', fn: (ev: { key: 'up' | 'down' }) => void): Promise<PluginListenerHandle>
  addListener(event: 'launchTab', fn: (ev: { tab: string }) => void): Promise<PluginListenerHandle>
}

export const KursorNative = registerPlugin<KursorNativePlugin>('KursorNative')
