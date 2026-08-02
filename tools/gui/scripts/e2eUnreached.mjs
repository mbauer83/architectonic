/**
 * Which source files did the browser suite never execute?
 *
 * `tests/e2e/coverage-fixture.ts` has always written Istanbul counters to `.nyc_output/` on every
 * navigation, and its own docstring said they "are merged by `nyc report`". There was no merge step in
 * `package.json` — collected every run, read by nothing. Merged, they answer the question the operation
 * register answers for REST: what ships but is never exercised.
 *
 * This is a *reachability* signal, not an assertion-backed one. A file appearing here was not loaded
 * and run by any flow, which is a strong statement. A file absent from here was executed — which says
 * nothing about whether anything checked what it did. Never gate on the second reading.
 *
 * Reads the merged `coverage-e2e/coverage-final.json` that `npm run coverage:e2e` writes, so the merge
 * lives in `nyc` rather than being re-implemented here.
 */
import { readdirSync, readFileSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const GUI_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const MERGED = join(GUI_ROOT, 'coverage-e2e', 'coverage-final.json')

/**
 * Every file `vite-plugin-istanbul` would instrument, whether or not the browser ever loaded it.
 *
 * This is the part a merged report cannot tell you on its own, and getting it wrong understates the
 * gap by the worst cases. Istanbul counters live in `window.__coverage__`, which only gains an entry
 * when the *chunk holding that file is loaded*. A view behind a lazily-imported route that no test
 * ever visits contributes no entry at all — so reading only the report's own keys reports it as
 * neither reached nor unreached, but as absent, which rounds to "fine".
 *
 * **`.ts` only, and that is a limitation rather than a choice.** `vite.config.ts` asks
 * `vite-plugin-istanbul` for `extension: ['.ts', '.vue']`, and the merged report contains **zero**
 * `.vue` entries: `@vitejs/plugin-vue` hands the plugin ids like `App.vue?vue&type=script&setup=true`,
 * and the extension filter does not match them. So single-file components — the views this signal
 * would be most useful about — are outside it. Counting them as candidates would report `App.vue`,
 * which every flow executes, as never loaded; 233 files arrived that way on the first run. Until the
 * filter reaches SFCs, the honest scope is `.ts`.
 */
const CANDIDATE_EXT = /\.ts$/
const IS_TEST = /\.(test|test-d|spec)\.[cm]?tsx?$/
const SKIP_DIRS = new Set(['__tests__', 'node_modules'])
const SKIP_FILES = new Set(['vite-env.d.ts'])

const instrumentableFiles = (dir) => {
  const found = []
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      if (SKIP_DIRS.has(entry.name)) continue
      found.push(...instrumentableFiles(join(dir, entry.name)))
    } else if (
      CANDIDATE_EXT.test(entry.name)
      && !IS_TEST.test(entry.name)
      && !entry.name.endsWith('.d.ts')
      && !SKIP_FILES.has(entry.name)
    ) {
      found.push(relative(GUI_ROOT, join(dir, entry.name)))
    }
  }
  return found
}

/** `src/ui/views/EntitiesView.vue` → `views`; the grouping a reader actually wants. */
const bucketOf = (path) => {
  const parts = path.split('/')
  const ui = parts.indexOf('ui')
  if (ui >= 0 && parts.length > ui + 1) return parts[ui + 1]
  return parts.length > 1 ? parts[1] : '.'
}

let merged
try {
  merged = JSON.parse(readFileSync(MERGED, 'utf8'))
} catch {
  process.stderr.write(
    `No merged coverage at ${relative(GUI_ROOT, MERGED)}.\n\n`
    + 'The signal needs an instrumented bundle and a browser run over it:\n'
    + '  npm run build:coverage\n'
    + '  E2E_BASE_URL=http://localhost:8000 npm run test:e2e\n'
    + '  npm run coverage:e2e:unreached\n\n'
    + 'An uninstrumented build collects nothing, silently — the fixture is a no-op without\n'
    + 'VITE_COVERAGE=true, so an empty .nyc_output means the bundle, not the suite.\n',
  )
  process.exit(1)
}

const executed = (counters) => Object.values(counters ?? {}).some((count) => count > 0)

const reported = new Map()
for (const [absolute, entry] of Object.entries(merged)) {
  const path = relative(GUI_ROOT, absolute)
  if (path.startsWith('src/')) reported.set(path, entry)
}

const candidates = instrumentableFiles(join(GUI_ROOT, 'src')).sort()
if (candidates.length === 0) {
  process.stderr.write('Found no instrumentable files under src/.\n')
  process.exit(1)
}

/** Three classes, worst first. The distinction is the point: "never loaded" is not "never asserted". */
const neverLoaded = []
const loadedNeverRun = []
const executedFiles = []
for (const path of candidates) {
  const entry = reported.get(path)
  if (!entry) {
    neverLoaded.push(path)
  } else if (Object.keys(entry.statementMap ?? {}).length === 0) {
    executedFiles.push(path) // nothing to execute — a types-only or re-export module
  } else {
    (executed(entry.s) ? executedFiles : loadedNeverRun).push(path)
  }
}

const pct = ((executedFiles.length / candidates.length) * 100).toFixed(1)
process.stdout.write(
  `Browser-suite reachability: ${executedFiles.length} of ${candidates.length} instrumentable files `
  + `under src/ were executed (${pct}%).\n\n`,
)

const report = (label, paths, note) => {
  if (paths.length === 0) return
  const byBucket = new Map()
  for (const path of paths) {
    const bucket = bucketOf(path)
    if (!byBucket.has(bucket)) byBucket.set(bucket, [])
    byBucket.get(bucket).push(path)
  }
  process.stdout.write(`${paths.length} ${label}:\n  ${note}\n`)
  for (const [bucket, bucketPaths] of [...byBucket].sort((a, b) => b[1].length - a[1].length)) {
    process.stdout.write(`\n  ${bucket} (${bucketPaths.length})\n`)
    for (const path of bucketPaths) process.stdout.write(`    ${path}\n`)
  }
  process.stdout.write('\n')
}

report(
  'never loaded',
  neverLoaded,
  'No chunk carrying these was ever fetched — a lazily-routed module no test visits, or a type-only\n  module that emits no runtime code at all and so legitimately has no counters.',
)
report(
  'loaded but never executed',
  loadedNeverRun,
  'The browser had these in memory and ran none of their statements.',
)

if (neverLoaded.length === 0 && loadedNeverRun.length === 0) {
  process.stdout.write('Every instrumentable file was executed by some flow.\n')
} else {
  process.stdout.write(
    'A file in either list ships and no browser flow has run it. That is where the next spec goes.\n'
    + 'Absent from both lists means executed — which says nothing about whether anything checked what\n'
    + 'it did. Never read this as assertion coverage.\n',
  )
}
