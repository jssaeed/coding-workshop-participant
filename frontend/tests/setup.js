// Runs before every test file (see vite.config.js "test.setupFiles").
//
// jsdom lacks a few browser APIs that Ant Design components call on mount.
// They are stubbed here so a page can render; nothing here changes what the
// tests assert.

import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

// Ant Design's responsive Table/Grid ask matchMedia which breakpoints apply.
// Say "all of them", so columns marked responsive: ['md'] are shown.
window.matchMedia = window.matchMedia || function matchMedia(query) {
  return {
    matches: true,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  }
}

// Table and Select measure themselves with ResizeObserver.
window.ResizeObserver = window.ResizeObserver || class ResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

// Unmount rendered trees and forget the session between tests.
afterEach(() => {
  cleanup()
  localStorage.clear()
  vi.restoreAllMocks()
})
