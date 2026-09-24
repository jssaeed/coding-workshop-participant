import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 3000
  },
  // Vitest (npm test). Tests live in tests/, mirroring src/. See tests/README.md.
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./tests/setup.js'],
    // .env.local points VITE_API_URL at the local proxy; tests use relative URLs.
    env: { VITE_API_URL: '' },
    // Results go to the project-wide test-results/ folder (gitignored)
    reporters: ['default', 'junit'],
    outputFile: { junit: '../test-results/frontend/junit.xml' },
    include: ['tests/**/*.test.{js,jsx}'],
    css: false,
    coverage: {
      provider: 'v8',
      include: ['src/**/*.{js,jsx}'],
      exclude: ['src/main.jsx'],
      reporter: ['text', 'html', 'json-summary'],
      reportsDirectory: '../test-results/frontend/coverage',
    },
  },
})
