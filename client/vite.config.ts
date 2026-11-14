import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// In development the Kursor daemon must run with `--dev`; Vite proxies API and
// WebSocket traffic to it so the browser only ever talks to one origin.
const backend = process.env.KURSOR_BACKEND ?? 'https://localhost:8443'

export default defineConfig({
  plugins: [react(), tailwindcss()],
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
