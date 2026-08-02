/**
 * Run-wide setup: fail immediately when the target stack cannot support the run, and reset the media
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

/**
 * The assurance store must be open, and this is where that is established.
 *
 * Twenty-one of the 150 chromium tests read the confidential store. Restarting the backend leaves it
 * activated but not *held*, and `arch-assurance unlock` is what tells the running process to hold it —
 * so a run started after a restart fails those twenty-one on navigation and visibility timeouts, twenty
 * seconds apiece, in ways that read as GUI defects. The handoff documents that trap, which is the
 * problem: a precondition a human has to remember is a precondition the harness should assert.
 *
 * One probe, before any test starts, naming the command that fixes it. A locked store is not a reason
 * to skip those tests either — they are the only coverage the assurance surface has, and a run that
 * quietly omitted them would report a green suite over an untested third of the product.
 */
const assuranceStoreState = async (baseURL: string): Promise<{ unlocked: boolean; detail: string }> => {
  try {
    const response = await fetch(new URL('/api/assurance/status', baseURL), {
      signal: AbortSignal.timeout(PROBE_TIMEOUT_MS),
    })
    if (!response.ok) return { unlocked: false, detail: `HTTP ${response.status}` }
    const body = await response.json() as { status?: string; unlocked?: boolean }
    return {
      unlocked: body.unlocked === true,
      detail: `status=${body.status ?? 'unknown'}`,
    }
  } catch (error) {
    return { unlocked: false, detail: error instanceof Error ? error.message : String(error) }
  }
}

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

  const store = await assuranceStoreState(baseURL)
  if (!store.unlocked) {
    throw new Error(
      `The assurance store is not open at ${baseURL} (${store.detail}).\n\n`
      + 'Twenty-one tests read the confidential store. Each would have waited out a navigation or '
      + 'visibility timeout and reported what looks like a GUI defect, so this run stops here '
      + 'instead.\n\n'
      + '  uv run arch-assurance unlock\n\n'
      + 'Activation is not enough: a restarted backend has the key but is not holding the store, and '
      + '`unlock` is what tells the running process to hold it. `arch-assurance status` says which of '
      + 'the two states you are in.',
    )
  }

  // Only for a media run: an e2e-only invocation must not clear a manifest it never rewrites.
  // Reusing the helper rather than re-deriving the manifest path, so there is one place that knows
  // where it lives.
  if (config.projects.some((project) => project.name === MEDIA_PROJECT)) {
    resetManifest()
  }
}
