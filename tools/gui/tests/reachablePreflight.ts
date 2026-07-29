/**
 * Run-wide setup: fail immediately when the target stack is unreachable, and reset the media
 * manifest once.
 *
 * Without this, an unreachable base URL is the quietest possible failure: every `page.goto` waits out
 * its own navigation timeout, so a run against nothing takes minutes, prints nothing until the end,
 * and then reports N unrelated-looking test failures. A media run behaves worst of all — it produces
 * no figures and no error until every capture has timed out in turn.
 *
 * One probe, before any test starts, naming the URL it tried and the two ways to fix it.
 *
 * The manifest reset lives here rather than in a spec's `beforeAll` for a reason found the hard way:
 * it used to sit in `media.spec.ts`, so it ran *between* spec files. Playwright takes them in
 * filename order, and a new spec sorting before `media.spec.ts` had its entries written and then
 * wiped — the figure appeared on disk while the manifest denied it existed. Resetting once, before
 * any spec, makes the order irrelevant.
 */
import type { FullConfig } from '@playwright/test'

import { resetManifest } from './media/mediaHelpers'

const PROBE_TIMEOUT_MS = 5_000
const MEDIA_PROJECT = 'media'

export default async function preflight(config: FullConfig): Promise<void> {
  const baseURL = config.projects[0]?.use?.baseURL
  if (!baseURL) return

  let reachable = false
  let detail = ''
  try {
    const response = await fetch(baseURL, {
      signal: AbortSignal.timeout(PROBE_TIMEOUT_MS),
      redirect: 'manual',
    })
    // Any HTTP answer means something is serving. A 404 at the root would still let routed pages
    // load, so the probe deliberately checks for a reply rather than for a status.
    reachable = true
    detail = `HTTP ${response.status}`
  } catch (error) {
    detail = error instanceof Error ? error.message : String(error)
  }

  if (!reachable) {
    throw new Error(
      `Cannot reach ${baseURL} (${detail}).\n\n`
      + 'Every test would have waited out its navigation timeout and told you nothing, so this run '
      + 'stops here instead.\n\n'
      + 'Start the stack, or point the run at one that is already up:\n'
      + '  • built SPA served by the backend — E2E_BASE_URL=http://localhost:8000\n'
      + '  • Vite dev server (proxies /api to the backend) — npm run dev, then :5173\n\n'
      + 'Figures are shot against the built SPA, which is why `npm run media` defaults to :8000: a '
      + 'screenshot has to show shipped code rather than whatever the dev server is holding.',
    )
  }

  // Only for a media run: an e2e-only invocation must not clear a manifest it never rewrites.
  // Reusing the helper rather than re-deriving the manifest path, so there is one place that knows
  // where it lives.
  if (config.projects.some((project) => project.name === MEDIA_PROJECT)) {
    resetManifest()
  }
}
