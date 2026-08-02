import { defineConfig } from 'vitest/config'

/**
 * The conformance suite: the real client's decoders over a real backend's bytes.
 *
 * A config of its own rather than an entry in `vite.config.ts`'s `test.include`, because the two
 * suites answer to different preconditions. `npm test` must run with nothing else started — it is a
 * pre-commit gate. This one needs a server, so folding it into the same run would either make the
 * unit suite require a backend or make this one skip when there is none, and a conformance suite
 * that skips is one that gets quoted as evidence for nothing.
 *
 * `jsdom`, pointed at the backend's origin. Two things need it and both are the *real* client's
 * requirements rather than the harness's: `buildUrl` resolves against `window.location.origin`, and
 * a rendered entity's Markdown goes through DOMPurify, which needs a document. Shimming a bare
 * `window.location` instead ran the adapters but stopped at the first entity read — so the shim
 * would have quietly excluded the two reads that render content.
 */
const baseUrl = (
  process.env.E2E_BASE_URL ?? process.env.CONFORMANCE_BASE_URL ?? 'http://localhost:8000'
).replace(/\/$/, '')

export default defineConfig({
  test: {
    environment: 'jsdom',
    environmentOptions: { jsdom: { url: `${baseUrl}/` } },
    include: ['tests/conformance/**/*.conformance.test.ts'],
    // One file at a time: the steps share a live backend and a discovered seed, and interleaving two
    // files' discovery would make a failure's cause ambiguous.
    fileParallelism: false,
    testTimeout: 120_000,
    hookTimeout: 120_000,
  },
})
