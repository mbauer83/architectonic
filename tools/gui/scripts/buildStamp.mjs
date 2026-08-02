/**
 * A fingerprint of the inputs a bundle was built from, so a run can tell whether `dist/` is current.
 *
 * `npm run test:e2e` drives the *built* SPA that the backend serves out of `dist/`. Nothing asserted
 * that the bundle came from the working tree, so the quietest possible failure was available: edit a
 * view, forget to rebuild, watch 152 tests pass against the previous bundle, and read that as
 * evidence about code the browser never loaded. A green run over a stale bundle is worse than a red
 * one, because it is indistinguishable from success.
 *
 * Written by `postbuild` and read by `tests/reachablePreflight.ts`.
 *
 * Only inputs that reach the bundle count. Test files under `src/` do not — Vite never sees them —
 * and including them would declare the bundle stale every time a unit test changed, which trains
 * people to ignore the check.
 */
import { createHash } from 'node:crypto'
import { readdirSync, readFileSync, statSync, writeFileSync } from 'node:fs'
import { dirname, join, relative, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const GUI_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')

/** Files outside `src/` that change what the bundle is. */
const ROOT_INPUTS = [
  'index.html',
  'vite.config.ts',
  'package.json',
  'package-lock.json',
  'tsconfig.json',
  'tsconfig.app.json',
]

const IS_TEST = /\.(test|test-d|spec)\.[cm]?tsx?$/
const SKIP_DIRS = new Set(['__tests__', 'node_modules'])

const sourceFiles = (dir) => {
  const found = []
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.isDirectory()) {
      if (SKIP_DIRS.has(entry.name)) continue
      found.push(...sourceFiles(join(dir, entry.name)))
    } else if (!IS_TEST.test(entry.name)) {
      found.push(join(dir, entry.name))
    }
  }
  return found
}

/** The fingerprint: every bundled input's path and content, in a stable order. */
export const computeSourceHash = () => {
  const paths = [
    ...sourceFiles(join(GUI_ROOT, 'src')),
    ...ROOT_INPUTS.map((name) => join(GUI_ROOT, name)),
  ]
    .filter((path) => {
      try {
        return statSync(path).isFile()
      } catch {
        return false
      }
    })
    .map((path) => relative(GUI_ROOT, path))
    .sort()

  const hash = createHash('sha256')
  for (const path of paths) {
    hash.update(path)
    hash.update('\0')
    hash.update(readFileSync(join(GUI_ROOT, path)))
    hash.update('\0')
  }
  return { hash: hash.digest('hex'), fileCount: paths.length }
}

export const STAMP_PATH = join(GUI_ROOT, 'dist', 'build-stamp.json')

/** The stamp `postbuild` writes. No timestamp: it would make two builds of one tree differ. */
export const readStamp = () => {
  try {
    return JSON.parse(readFileSync(STAMP_PATH, 'utf8'))
  } catch {
    return null
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const { hash, fileCount } = computeSourceHash()
  writeFileSync(STAMP_PATH, `${JSON.stringify({ hash, fileCount }, null, 2)}\n`)
  process.stdout.write(`build stamp: ${hash.slice(0, 12)} over ${fileCount} bundled inputs\n`)
}
