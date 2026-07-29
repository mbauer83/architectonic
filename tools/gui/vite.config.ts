import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import istanbul from 'vite-plugin-istanbul'

const backendTarget = 'http://127.0.0.1:8000'

// Opt-in Istanbul instrumentation for E2E coverage (VITE_COVERAGE=true npm run build).
// Off by default, so the shipped production build is never instrumented. The resulting
// build records browser-side execution in window.__coverage__, which the Playwright
// route-walk collects as a *reachability* signal over .vue/composables (report-only,
// never gated — see the e2e job + tests/e2e/coverage-fixture.ts).
const e2eCoverage = process.env.VITE_COVERAGE === 'true'

export default defineConfig({
  plugins: [
    vue(),
    ...(e2eCoverage
      ? [
          istanbul({
            include: 'src/**',
            exclude: ['src/**/*.test.ts', 'src/domain/types.generated.ts'],
            extension: ['.ts', '.vue'],
            // The E2E build is a production `vite build`; instrument it anyway (the plugin
            // skips production by default to avoid shipping instrumented code).
            forceBuildInstrument: true,
          }),
        ]
      : []),
  ],
  test: {
    environment: 'node',
    include: ['src/**/*.test.ts'],
    coverage: {
      provider: 'v8',
      // text for the CI log; lcov for the Codecov upload; json-summary for local glances.
      reporter: ['text-summary', 'lcov', 'json-summary'],
      include: ['src/**/*.ts', 'src/**/*.vue'],
      exclude: ['src/**/*.test.ts', 'src/domain/types.generated.ts', 'src/main.ts'],
      // Gate ONLY the logic-heavy directories where unit tests are the right tool.
      // .vue views/components and composables are wiring covered by the Playwright
      // route-walk (see e2e job), so they are measured + reported but not gated here.
      // Thresholds are seeded just below current coverage as a regression floor and
      // are meant to ratchet upward over time (cf. the backend fail_under ratchet).
      thresholds: {
        'src/domain/**': { statements: 90, lines: 90, functions: 80, branches: 80 },
        'src/ui/lib/**': { statements: 33, lines: 35, functions: 20, branches: 18 },
      },
    },
  },
  server: {
    proxy: {
      // SSE: long-lived event stream — must NOT inherit the 10s timeout below,
      // or the dev proxy severs it (ERR_EMPTY_RESPONSE + reconnect storm).
      // Listed before '/api' so the more specific context matches first.
      '/api/events': {
        target: backendTarget,
        changeOrigin: true,
      },
      // Viewpoint execution/derived-neighbor lookups can legitimately take several
      // seconds (bounded relationship derivation over the scoped population), and every
      // execution surface fires two of these concurrently (content + projection) — the
      // generic 10s timeout below was silently killing both mid-flight under that
      // concurrent load (ERR_EMPTY_RESPONSE in the browser even though the backend
      // itself completes in ~5-6s; reproduced directly against this proxy with two
      // simultaneous curl requests). Matches the frontend's own longer client-side fetch
      // timeout for these same routes (`VIEWPOINT_EXECUTION_TIMEOUT_MS` in
      // `HttpModelRepository.ts`). Listed before '/api' so the more specific context
      // matches first.
      '/api/viewpoints/execute': {
        target: backendTarget,
        changeOrigin: true,
        timeout: 65000,
        proxyTimeout: 65000,
      },
      '/api/neighbors': {
        target: backendTarget,
        changeOrigin: true,
        timeout: 65000,
        proxyTimeout: 65000,
      },
      '/api': {
        target: backendTarget,
        changeOrigin: true,
        timeout: 10000,
        proxyTimeout: 10000,
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyReq, req) => {
            console.log(`[vite-proxy] ${req.method} ${req.url} -> ${backendTarget}${proxyReq.path ?? '/'}`)
          })
          proxy.on('error', (err, req) => {
            console.error(`[vite-proxy] ${req.method} ${req.url} failed:`, err.message)
          })
        },
      },
      '/admin/api': {
        target: backendTarget,
        changeOrigin: true,
        timeout: 10000,
        proxyTimeout: 10000,
        configure: (proxy) => {
          proxy.on('proxyReq', (proxyReq, req) => {
            console.log(`[vite-proxy] ${req.method} ${req.url} -> ${backendTarget}${proxyReq.path ?? '/'}`)
          })
          proxy.on('error', (err, req) => {
            console.error(`[vite-proxy] ${req.method} ${req.url} failed:`, err.message)
          })
        },
      },
    },
  },
})
