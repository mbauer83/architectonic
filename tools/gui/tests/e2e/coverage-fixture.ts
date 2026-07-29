/**
 * Navigation-safe Istanbul coverage collection for the E2E route-walk.
 *
 * The app is built with `VITE_COVERAGE=true` (vite-plugin-istanbul), so the browser
 * accumulates execution counters in `window.__coverage__`. A full page load resets that
 * object, and several smoke tests do multiple `page.goto(...)`, so we flush on every
 * `beforeunload` (via an exposed binding) plus once more at the end of each test.
 *
 * The per-test JSON files in `.nyc_output/` are merged by `nyc report` into lcov, which
 * CI uploads to Codecov under the `frontend-e2e` flag. This is a *reachability* signal
 * (code executed during real flows), reported separately and never gated — distinct from
 * the assertion-backed unit coverage. Collection is a no-op for an uninstrumented build,
 * so the fixture is safe to use whether or not VITE_COVERAGE was set.
 */
import { randomUUID } from 'node:crypto'
import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'

import { test as base, expect } from '@playwright/test'

const NYC_OUTPUT_DIR = join(process.cwd(), '.nyc_output')

const persist = (coverageJSON: string): void => {
  if (!coverageJSON) return
  mkdirSync(NYC_OUTPUT_DIR, { recursive: true })
  writeFileSync(join(NYC_OUTPUT_DIR, `e2e-${randomUUID()}.json`), coverageJSON)
}

export const test = base.extend({
  context: async ({ context }, use) => {
    await context.exposeFunction('__flushIstanbulCoverage', persist)
    await context.addInitScript(() =>
      window.addEventListener('beforeunload', () => {
        const cov = (window as unknown as { __coverage__?: unknown }).__coverage__
        if (cov) void (window as unknown as { __flushIstanbulCoverage: (s: string) => void })
          .__flushIstanbulCoverage(JSON.stringify(cov))
      }),
    )

    await use(context)

    // Final flush for the page(s) still open at test end (no further unload fires).
    for (const page of context.pages()) {
      const cov = await page.evaluate(() => (window as unknown as { __coverage__?: unknown }).__coverage__)
      if (cov) persist(JSON.stringify(cov))
    }
  },
})

export { expect }
