import { readFileSync } from 'node:fs'
import { defineConfig } from 'vitest/config'
import type { ProxyOptions } from 'vite'
import vue from '@vitejs/plugin-vue'
import istanbul from 'vite-plugin-istanbul'

const backendTarget = 'http://127.0.0.1:8000'

// The REST surface's timeout classification, generated from the route-policy manifest. Read as
// data rather than imported as a module: this config and the app are two TypeScript programs, and a
// module can only be owned by one of them. Nothing is derived here — the proxy context patterns and
// their ordering arrive already computed, so this reading and the client's cannot diverge.
type TimeoutPolicy = {
  budgetMs: Record<string, number | null>
  proxyHeadroomMs: number
  proxyContexts: Record<string, string[]>
}

const policy = JSON.parse(
  readFileSync(new URL('./src/adapters/http/routeTimeoutPolicy.json', import.meta.url), 'utf8'),
) as TimeoutPolicy

const proxyTimeoutMs = (timeoutClass: string): number | undefined => {
  const budget = policy.budgetMs[timeoutClass]
  return budget === null ? undefined : budget + policy.proxyHeadroomMs
}

const DEFAULT_PROXY_TIMEOUT_MS = (policy.budgetMs.default ?? 0) + policy.proxyHeadroomMs

const logProxy: ProxyOptions['configure'] = (proxy) => {
  proxy.on('proxyReq', (proxyReq, req) => {
    console.log(`[vite-proxy] ${req.method} ${req.url} -> ${backendTarget}${proxyReq.path ?? '/'}`)
  })
  proxy.on('error', (err, req) => {
    console.error(`[vite-proxy] ${req.method} ${req.url} failed:`, err.message)
  })
}

/**
 * Proxy contexts for one timeout class, keyed by the regular expressions the shared policy
 * derives from the route templates. A `streaming` class has no budget at all — omitting
 * `timeout` is what keeps the dev proxy from severing the event stream and triggering a
 * reconnect storm.
 */
const contextsFor = (timeoutClass: 'streaming' | 'derived-graph'): Record<string, ProxyOptions> => {
  const budget = proxyTimeoutMs(timeoutClass)
  return Object.fromEntries(
    policy.proxyContexts[timeoutClass].map((context) => [
      context,
      {
        target: backendTarget,
        changeOrigin: true,
        configure: logProxy,
        ...(budget === undefined ? {} : { timeout: budget, proxyTimeout: budget }),
      },
    ]),
  )
}

const streamingContexts = contextsFor('streaming')
const derivedGraphContexts = contextsFor('derived-graph')

// Opt-in Istanbul instrumentation for E2E coverage (VITE_COVERAGE=true npm run build).
// Off by default, so the shipped production build is never instrumented. The resulting
// build records browser-side execution in window.__coverage__, which the Playwright
// route-walk collects as a *reachability* signal over .vue/composables (report-only,
// never gated — see the e2e job + tests/e2e/coverage-fixture.ts).
const e2eCoverage = process.env.VITE_COVERAGE === 'true'

// What to instrument, stated once. `nyc report` merges what the browser collected and applies these
// same three filters again, from the same file — `vite-plugin-istanbul` and `nyc` both read `.nycrc`,
// and having each default independently is exactly how the signal lost every SFC: the instrumented
// bundle carried 214 `.vue` files and the merged report showed none, because nyc's own default
// extension list has no `.vue` in it and nothing here contradicted it.
const nycConfig = JSON.parse(
  readFileSync(new URL('./.nycrc.json', import.meta.url), 'utf8'),
) as { extension: string[], include: string[], exclude: string[] }

export default defineConfig({
  plugins: [
    vue(),
    ...(e2eCoverage
      ? [
          istanbul({
            include: nycConfig.include,
            exclude: nycConfig.exclude,
            extension: nycConfig.extension,
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
      // Streaming and derived-graph contexts come from the shared timeout classification,
      // most specific first, so the dev proxy cannot disagree with the client's own budget —
      // and so a renamed route carries its budget with it instead of silently falling to the
      // generic rule below. Templates, not prefixes: identity now sits inside the path, and
      // `/api/entities/{id}/neighbors` has no prefix that separates it from an entity read.
      ...streamingContexts,
      ...derivedGraphContexts,
      '/api': {
        target: backendTarget,
        changeOrigin: true,
        timeout: DEFAULT_PROXY_TIMEOUT_MS,
        proxyTimeout: DEFAULT_PROXY_TIMEOUT_MS,
        configure: logProxy,
      },
      '/admin/api': {
        target: backendTarget,
        changeOrigin: true,
        timeout: DEFAULT_PROXY_TIMEOUT_MS,
        proxyTimeout: DEFAULT_PROXY_TIMEOUT_MS,
        configure: logProxy,
      },
    },
  },
})
