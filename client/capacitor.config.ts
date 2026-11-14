import type { CapacitorConfig } from '@capacitor/cli'

// appId is permanent once published on Google Play: change it *before* the
// first upload if you prefer a domain you own (reverse-DNS form).
const config: CapacitorConfig = {
  appId: 'io.github.makadv.padlink',
  appName: 'PadLink',
  webDir: 'dist',
  server: {
    // Bundled assets are served from https://localhost (the server allow-lists this origin).
    androidScheme: 'https',
  },
  android: {
    allowMixedContent: false,
    webContentsDebuggingEnabled: false,
  },
}

export default config
