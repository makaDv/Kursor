import { defineConfig, type Plugin } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// In development the PadLink daemon must run with `--dev`; Vite proxies API and
// WebSocket traffic to it so the browser only ever talks to one origin.
const backend = process.env.PADLINK_BACKEND ?? 'https://localhost:8443'

// Content-Security-Policy for the bundled store apps (the PWA also gets a stricter
// header from the server; both apply). Build only: the Vite dev server needs inline scripts.
// The WebView never talks to the network itself (traffic goes through the native
// plugin), so 'self' is enough; wss:/https: remain for the PWA's same-host socket.
const CSP =
  "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; " +
  "connect-src 'self' wss: https:; worker-src 'self'; manifest-src 'self'; object-src 'none'; " +
  "base-uri 'none'; form-action 'self'"

function cspMeta(): Plugin {
  return {
    name: 'padlink-csp',
    apply: 'build',
    transformIndexHtml: () => [
      { tag: 'meta', attrs: { 'http-equiv': 'Content-Security-Policy', content: CSP }, injectTo: 'head-prepend' },
    ],
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss(), cspMeta()],
  build: {
    outDir: 'dist',
    sourcemap: false,
    target: 'es2020',
  },
  server: {
    host: true,
    port: 5173,
    proxy: {
      '/api': { target: backend, secure: false },
      '/ca.crt': { target: backend, secure: false },
      '/ws': { target: backend, secure: false, ws: true },
    },
  },
})
