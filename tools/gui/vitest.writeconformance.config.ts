import { defineConfig } from 'vitest/config'

/**
 * The write half of the conformance suite, which needs a repository it may destroy.
 *
 * Separate from `vitest.conformance.config.ts` for the same reason that one is separate from
 * `vite.config.ts`: the suites answer to different preconditions, and folding a stricter one into a
 * looser gate makes the looser gate wrong. The read conformance runs against any backend, including the
 * developer's. This one authors and deletes on every step, so it runs only against the disposable
 * workspace `tools/quality/gui_write_walk.py` builds — and refuses, rather than skipping, without it.
 *
 * Not runnable as `npm run` on its own on purpose: there is no origin to default to. The orchestrator
 * is the entry point, and it is a Python one because the fixture is.
 */
const baseUrl = (process.env.E2E_BASE_URL ?? '').replace(/\/$/, '')

export default defineConfig({
  test: {
    environment: 'jsdom',
    // The same reason as the read config: `buildUrl` resolves against `window.location.origin`, so a
    // jsdom pointed anywhere else would have the adapters writing to the wrong host.
    environmentOptions: { jsdom: { url: `${baseUrl || 'http://127.0.0.1:1'}/` } },
    include: ['tests/conformance/writes.conformance.test.ts'],
    fileParallelism: false,
    testTimeout: 300_000,
    hookTimeout: 300_000,
  },
})
