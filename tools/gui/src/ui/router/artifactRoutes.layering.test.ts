import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'
import { ROUTE_TEMPLATES } from './artifactRoutes'

/**
 * Nothing inward of the delivery layer spells a GUI route.
 *
 * `eslint.config.js` already forbids `domain/`, `adapters/` and `ports/` from *importing* `ui/`. It
 * could not see the violation it was written for: `artifactLinks.ts` sat in `domain/` emitting
 * `'/entity?id='` strings for months, importing nothing. An emitted string is the same dependency as
 * an import — the model layer deciding what a URL looks like — and it is the more durable one,
 * because it survives every refactor of the module graph. `domain/` and `ports/` are clean only
 * because a migration moved that module out.
 *
 * The vocabulary is derived from `ROUTE_TEMPLATES` rather than listed, so a route added to the
 * catalogue is covered without editing this test. Both spellings are refused: the plural collection
 * as it exists now, and the singular-with-query form the migration removed — the shape that hid here
 * once is the shape most likely to be reintroduced by someone working from an old example.
 *
 * **`adapters/` is out of scope, deliberately.** It addresses the REST surface, whose collections are
 * spelled with the same words: `buildUrl('/entities')` is correct there and identical to the string
 * refused here. Distinguishing them needs the base URL, which is the adapter's own; a rule that
 * cannot tell them apart would either pass everything or fail the whole HTTP adapter.
 */

const SRC_ROOT = join(import.meta.dirname, '..', '..')

const SCANNED_ROOTS = ['domain', 'ports'] as const

/**
 * Excluded because it is types with no runtime representation: it cannot emit anything, and the REST
 * paths it does name — `/api/entities` and its siblings — are the backend's addresses, not the GUI's.
 */
const GENERATED = 'openapi.generated.ts'

/** `entities`, `diagrams`, … — the first segment of every canonical route. */
const collectionSegments = (): readonly string[] => {
  const segments = Object.values(ROUTE_TEMPLATES)
    .map((template) => template.split('/')[1])
    .filter((segment): segment is string => segment !== undefined && !segment.startsWith(':'))
  return [...new Set(segments)].sort()
}

/**
 * The singular of a collection segment, for the pre-migration `'/entity?id='` spelling.
 *
 * Crude on purpose: `matrices` → `matrice` is not a word, and it does not need to be — the point is
 * to refuse anything that reads as an address for one of these resources, and over-refusing a
 * non-word costs nothing. `entities` → `entitie` would miss the real case, so a trailing `ies`
 * becomes `y`.
 */
const singularOf = (segment: string): string =>
  segment.endsWith('ies') ? `${segment.slice(0, -3)}y` : segment.replace(/s$/, '')

const refusedPrefixes = (): readonly string[] => {
  const collections = collectionSegments()
  return [...new Set([...collections, ...collections.map(singularOf)])].sort()
}

const withoutComments = (source: string): string =>
  source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')

const sourceFiles = (dir: string): readonly string[] =>
  readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) return sourceFiles(full)
    return full.endsWith('.ts') && !full.endsWith(GENERATED) ? [full] : []
  })

const STRING_LITERAL = /['"`](\/[^'"`\n]*)['"`]/g

/** Every `<file>: <literal>` in `source` that addresses a GUI resource. */
const routeLiteralsIn = (source: string, prefixes: readonly string[]): readonly string[] => {
  const found: string[] = []
  for (const match of withoutComments(source).matchAll(STRING_LITERAL)) {
    const value = match[1]
    const segment = value.split('/')[1]?.split('?')[0]
    if (segment !== undefined && prefixes.includes(segment)) found.push(value)
  }
  return found
}

const offenders = (): readonly string[] => {
  const prefixes = refusedPrefixes()
  return SCANNED_ROOTS.flatMap((root) =>
    sourceFiles(join(SRC_ROOT, root)).flatMap((file) =>
      routeLiteralsIn(readFileSync(file, 'utf8'), prefixes).map(
        (literal) => `${file.slice(SRC_ROOT.length + 1)}: ${literal}`,
      ),
    ),
  )
}

describe('GUI route literals stay in the delivery layer', () => {
  it('finds none under domain/ or ports/', () => {
    expect(offenders()).toEqual([])
  })
})

describe('the layering scanner itself', () => {
  it('derives the refused vocabulary from the route catalogue', () => {
    const prefixes = refusedPrefixes()
    // A floor, not a count: the catalogue grows, and asserting its size would fail on every route
    // added rather than on anything this test is about.
    expect(prefixes.length).toBeGreaterThan(8)
    for (const expected of ['entities', 'entity', 'diagrams', 'diagram', 'documents', 'document']) {
      expect(prefixes).toContain(expected)
    }
  })

  it('refuses both spellings, and nothing that merely contains a slash', () => {
    const prefixes = refusedPrefixes()
    // The literal that hid in `domain/` for months, and its replacement.
    expect(routeLiteralsIn("const l = '/entity?id=' + id", prefixes)).toEqual(['/entity?id='])
    expect(routeLiteralsIn("const l = '/entities/' + id", prefixes)).toEqual(['/entities/'])
    // What the scanned modules legitimately contain: separators, repository paths, JSON pointers,
    // and the backend's own addresses.
    expect(routeLiteralsIn("parts.join('/')", prefixes)).toEqual([])
    expect(routeLiteralsIn("const p = '/repo/model/common/role/agent.md'", prefixes)).toEqual([])
    expect(routeLiteralsIn("const p = '/query/entity_criteria/attribute'", prefixes)).toEqual([])
    expect(routeLiteralsIn("buildUrl('/api/entities')", prefixes)).toEqual([])
  })

  it('reads a non-empty population of files', () => {
    // Without this, a walk that stopped matching would report no offenders over an empty scan.
    const scanned = SCANNED_ROOTS.flatMap((root) => sourceFiles(join(SRC_ROOT, root)))
    expect(scanned.length).toBeGreaterThan(30)
    expect(scanned.some((file) => file.endsWith('artifactLinks.ts'))).toBe(true)
  })
})
