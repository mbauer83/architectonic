import { defineConfig, devices } from '@playwright/test'

/**
 * E2E smoke configuration.
 *
 * Targets an already-running stack via E2E_BASE_URL, defaulting to the built SPA served by
 * arch-backend on :8000 — which is what CI drives and what ships. Point it at a Vite dev
 * server (`npm run dev`, :5173, proxying /api to :8000) to iterate on a spec.
 *
 * The default was :5173 until 0.2.1, and that made the gate mean two different things. With no
 * dev server up, `npm run test:e2e` failed its preflight and looked like a broken environment;
 * with one up, it passed against whatever the dev server was holding rather than against a
 * bundle anything had built. `npm run media` had already defaulted to :8000 for exactly this
 * reason — a figure has to show shipped code — and the smoke suite makes the same claim.
 *
 * These tests assert runtime wiring the unit suite cannot: that every route renders
 * without a 4xx/5xx API call, an uncaught console error, or an empty <main>.
 */
export default defineConfig({
  testDir: './tests',
  // Probe the base URL once, before anything runs. An unreachable stack is otherwise the quietest
  // failure available: each test waits out its own navigation timeout and the run says nothing for
  // minutes, then reports failures that look like test bugs rather than a missing server.
  globalSetup: './tests/reachablePreflight.ts',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: process.env.CI ? [['github'], ['list']] : 'list',
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:8000',
    trace: 'on-first-retry',
    viewport: { width: 1440, height: 900 },
  },
  projects: [
    {
      name: 'chromium',
      testMatch: /e2e\/.*\.spec\.ts/,
      use: { ...devices['Desktop Chrome'] },
    },
    {
      name: 'media',
      testMatch: /media\/.*\.spec\.ts/,
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1440, height: 900 },
        deviceScaleFactor: 2,
      },
    },
  ],
})
