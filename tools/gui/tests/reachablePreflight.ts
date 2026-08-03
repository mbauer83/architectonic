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
import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import type { FullConfig } from '@playwright/test'

// @ts-expect-error - plain ESM helper shared with the postbuild script; no type declarations by design
import { computeSourceHash, readStamp } from '../scripts/buildStamp.mjs'
import { resetManifest } from './media/mediaHelpers'

const PROBE_TIMEOUT_MS = 5_000
const SCHEMA_PROBE_TIMEOUT_MS = 20_000
//: Building the tree's document imports the whole application; generous, and bounded.
const SCHEMA_DUMP_TIMEOUT_MS = 120_000
const MEDIA_PROJECT = 'media'
const GUI_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')

/**
 * The served bundle must be the one this working tree builds.
 *
 * Two questions, and both have to hold. *Is `dist/` current?* — compare the stamp `postbuild` wrote
 * against a fingerprint recomputed now over every bundled input. *Is the server serving that `dist/`?*
 * — compare the hashed asset filenames in the served `index.html` against the local one. Either check
 * alone leaves a hole: a fresh `dist/` proves nothing if the backend is serving a copy from
 * somewhere else, and a matching server proves nothing if what it matches is three edits old.
 *
 * Skipped, with the reason named, when the target is not a built bundle — the Vite dev server
 * transforms on demand and references `/src/main.ts`, so there is nothing to be stale.
 */
/**
 * Whether the *backend* serving `baseURL` predates this tree's response contracts.
 *
 * The bundle check above covers the frontend half; this covers the half it does not. A backend left
 * running across a contract change serves the old field names while the freshly built SPA decodes the
 * new ones, so every read fails in the browser and the suite reports twenty GUI defects that do not
 * exist. That is not hypothetical: it cost an 8.8-minute run on 2026-08-03, when `specialization`
 * became `specializations` and a two-hour-old server kept answering with the former.
 *
 * The signal is the served document's own component schemas against the tree's. Comparing schemas
 * rather than the whole document keeps the check about the thing that breaks a decoder — a route's
 * *shape* — so a difference in summaries or tags does not stop a run that would have been fine.
 */
const staleBackendReason = async (baseURL: string): Promise<string | null> => {
  if (process.env.E2E_SKIP_BACKEND_CHECK === '1') return null

  let servedSchemas: string
  try {
    const response = await fetch(`${baseURL}/openapi.json`, {
      signal: AbortSignal.timeout(SCHEMA_PROBE_TIMEOUT_MS),
    })
    if (!response.ok) return null // not a backend origin (a bare Vite dev server has no such route)
    const document = (await response.json()) as { components?: { schemas?: unknown } }
    if (!document.components?.schemas) return null
    servedSchemas = stableJson(document.components.schemas)
  } catch {
    return null // reachability has its own probe, which runs first
  }

  let treeSchemas: string
  try {
    const dumped = execFileSync(
      'uv', ['run', 'tools/openapi/dump_openapi.py', '/dev/stdout'],
      { cwd: resolve(GUI_ROOT, '..', '..'), encoding: 'utf8', timeout: SCHEMA_DUMP_TIMEOUT_MS,
        stdio: ['ignore', 'pipe', 'ignore'] },
    )
    const document = JSON.parse(dumped) as { components?: { schemas?: unknown } }
    if (!document.components?.schemas) return null
    treeSchemas = stableJson(document.components.schemas)
  } catch {
    return null // cannot build the tree's document here; not a reason to block a run
  }

  if (servedSchemas === treeSchemas) return null
  return 'the response schemas it serves are not this tree\'s. Whatever is running was started before '
    + 'a contract change, so the browser decodes fields the server does not send.'
}

/** Key-ordered JSON, so two equal documents compare equal whatever order they were built in. */
const stableJson = (value: unknown): string =>
  JSON.stringify(value, (_key, inner) =>
    inner && typeof inner === 'object' && !Array.isArray(inner)
      ? Object.fromEntries(Object.entries(inner as Record<string, unknown>).sort(([a], [b]) => a.localeCompare(b)))
      : inner)


const staleBundleReason = async (baseURL: string): Promise<string | null> => {
  // An escape hatch, because there is one legitimate case: driving a bundle built elsewhere on
  // purpose. It has to be asked for, so forgetting to rebuild never silently takes it.
  if (process.env.E2E_SKIP_BUILD_CHECK === '1') return null

  let servedHtml: string
  try {
    const response = await fetch(baseURL, { signal: AbortSignal.timeout(PROBE_TIMEOUT_MS) })
    servedHtml = await response.text()
  } catch {
    return null // reachability is reported by its own probe, which runs first
  }

  const assetsOf = (html: string) => [...html.matchAll(/\/assets\/([\w.-]+\.(?:js|css))/g)]
    .map((match) => match[1])
    .sort()

  const servedAssets = assetsOf(servedHtml)
  if (servedAssets.length === 0) return null // a dev server, or an unbuilt target

  let localAssets: string[]
  try {
    localAssets = assetsOf(readFileSync(join(GUI_ROOT, 'dist', 'index.html'), 'utf8'))
  } catch {
    return 'the server is serving a built bundle, but there is no local dist/index.html to compare it '
      + 'against. Run `npm run build`.'
  }

  if (servedAssets.join() !== localAssets.join()) {
    return `the served bundle is not the local dist/. Served ${servedAssets.join(', ') || '(none)'}; `
      + `dist/ holds ${localAssets.join(', ') || '(none)'}. Whatever is being served was built from a `
      + 'different tree, so this run would report on code the browser never loads.'
  }

  const stamp = readStamp() as { hash?: string; fileCount?: number } | null
  if (!stamp?.hash) {
    return 'dist/ carries no build stamp, so its age cannot be established. Run `npm run build`.'
  }
  const { hash, fileCount } = computeSourceHash() as { hash: string; fileCount: number }
  if (hash !== stamp.hash) {
    return `dist/ was built from different sources than the working tree holds (stamp `
      + `${String(stamp.hash).slice(0, 12)} over ${stamp.fileCount} inputs; tree is `
      + `${hash.slice(0, 12)} over ${fileCount}). Run \`npm run build\`.`
  }
  return null
}

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

  const stale = await staleBundleReason(baseURL)
  if (stale) {
    throw new Error(
      `The bundle at ${baseURL} is not this working tree's: ${stale}\n\n`
      + 'Every test would have passed or failed against code you did not write, which is the one '
      + 'result worse than a red run, so this run stops here instead.\n\n'
      + 'Set E2E_SKIP_BUILD_CHECK=1 to run anyway — deliberately, against a bundle you know is not '
      + 'the tree.',
    )
  }

  const staleServer = await staleBackendReason(baseURL)
  if (staleServer) {
    throw new Error(
      `The backend at ${baseURL} is not this working tree's: ${staleServer}\n\n`
      + 'Every read would fail in the browser and the failures would read as GUI defects, so this run '
      + 'stops here instead.\n\n'
      + '  uv run arch-backend --restart --daemon && uv run arch-assurance unlock\n\n'
      + 'Set E2E_SKIP_BACKEND_CHECK=1 to run anyway — deliberately, against a server you know is not '
      + 'the tree.',
    )
  }

  // Only for a media run: an e2e-only invocation must not clear a manifest it never rewrites.
  // Reusing the helper rather than re-deriving the manifest path, so there is one place that knows
  // where it lives.
  if (config.projects.some((project) => project.name === MEDIA_PROJECT)) {
    resetManifest()
  }
}
