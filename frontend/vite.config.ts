import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

const apiTarget = process.env.VITE_API_PROXY_TARGET ?? 'http://localhost:8000'

// The app calls the API with same-origin relative paths, so both the dev server
// and `vite preview` must reverse-proxy these routes to the backend.
// Some API prefixes double as SPA routes (/portal, /admin, /tickets/:id), so a
// browser navigation (Accept: text/html) must get index.html, not the API.
function spaBypass(req: { headers: { accept?: string } }) {
  if (req.headers.accept?.includes('text/html')) return '/index.html'
}

const proxy = {
  '/auth': apiTarget,
  '/portal': { target: apiTarget, bypass: spaBypass },
  '/admin': { target: apiTarget, bypass: spaBypass },
  '/events': apiTarget,
  '/tickets': { target: apiTarget, ws: true, bypass: spaBypass },
  '/audit': apiTarget,
  '/customers': apiTarget,
  '/knowledge': apiTarget,
}

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: { proxy },
  preview: { proxy },
  test: {
    environment: 'jsdom',
    setupFiles: './src/test-setup.ts',
  },
})
