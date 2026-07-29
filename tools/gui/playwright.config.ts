import { defineConfig, devices } from '@playwright/test'

/**
 * E2E smoke configuration.
 *
 * Targets a already-running stack via E2E_BASE_URL (default: the Vite dev server on
 * :5173, which proxies /api to the backend on :8000). In CI the SPA is built and served
 * by arch-backend on :8000, so E2E_BASE_URL=http://localhost:8000.
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
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:5173',
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
