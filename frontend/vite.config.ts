import { fileURLToPath } from 'node:url'
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

const apiTarget = process.env.VITE_API_PROXY_TARGET ?? 'http://localhost:8000'

// The app calls the API with same-origin relative paths, so both the dev server
// and `vite preview` must reverse-proxy these routes to the backend.
const proxy = {
  '/auth': apiTarget,
  '/portal': {
    target: apiTarget,
    bypass(req: { headers: { accept?: string } }) {
      if (req.headers.accept?.includes('text/html')) return '/index.html'
    },
  },
  '/admin': {
    target: apiTarget,
    bypass(req: { headers: { accept?: string } }) {
      if (req.headers.accept?.includes('text/html')) return '/index.html'
    },
  },
  '/events': apiTarget,
  '/tickets': { target: apiTarget, ws: true },
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
