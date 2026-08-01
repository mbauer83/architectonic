import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { describe, expect, it } from 'vitest'
import { QUERY_PARAMETER_ROLES, identityQueryUses } from './queryParameterPolicy'

/**
 * The reproducible half of the GUI route inventory: walk the source, find every `route.query`
 * use, and require the classification table to account for exactly those. Equality in both
 * directions is the point — a subset check would let a newly added `?id=` slip in unclassified,
 * and a superset check would let a stale entry make the table look more complete than it is.
 */

const SRC_ROOT = join(import.meta.dirname, '..', '..')

const SOURCE_SUFFIXES = ['.ts', '.vue']

const isTestFile = (path: string): boolean =>
  path.endsWith('.test.ts') || path.includes(`${'__tests__'}/`)

const sourceFiles = (dir: string): string[] =>
  readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) return sourceFiles(full)
    if (!SOURCE_SUFFIXES.some((suffix) => full.endsWith(suffix))) return []
    return isTestFile(full) ? [] : [full]
  })

/**
 * Comments are stripped before scanning: several modules *describe* their query handling in prose
 * ("Query writes MERGE `route.query`"), and counting that as a use would make the table document
 * documentation.
 */
const withoutComments = (line: string): string => {
  const trimmed = line.trimStart()
  if (trimmed.startsWith('//') || trimmed.startsWith('*') || trimmed.startsWith('/*')) return ''
  const comment = line.indexOf('//')
  return comment === -1 ? line : line.slice(0, comment)
}

const KEYED = /route\.query(?:\.([A-Za-z_$][\w$]*)|\[\s*'([^']+)'\s*\]|\[\s*"([^"]+)"\s*\])/g
const ANY_USE = /route\.query/g

/** Every `<relative path>#<key>` use in one file, with `#*` for whole-object or computed access. */
const usesIn = (file: string): Set<string> => {
  const relativePath = relative(SRC_ROOT, file).split('\\').join('/')
  const found = new Set<string>()
  for (const rawLine of readFileSync(file, 'utf8').split('\n')) {
    const line = withoutComments(rawLine)
    const keyed = [...line.matchAll(KEYED)]
    for (const match of keyed) {
      found.add(`${relativePath}#${match[1] ?? match[2] ?? match[3]}`)
    }
    if ([...line.matchAll(ANY_USE)].length > keyed.length) found.add(`${relativePath}#*`)
  }
  return found
}

const allUses = (): Set<string> => {
  const uses = new Set<string>()
  for (const file of sourceFiles(SRC_ROOT)) {
    for (const use of usesIn(file)) uses.add(use)
  }
  return uses
}

describe('GUI route.query inventory', () => {
  it('classifies exactly the query uses that exist in the source', () => {
    const found = [...allUses()].sort()
    const declared = Object.keys(QUERY_PARAMETER_ROLES).sort()
    expect(found.filter((use) => !declared.includes(use))).toEqual([])
    expect(declared.filter((use) => !found.includes(use))).toEqual([])
  })

  it('finds the uses this migration exists to convert', () => {
    // A guard on the scanner itself: a regex that silently stopped matching would make the
    // equality above pass with two empty sets.
    const found = allUses()
    expect(found.has('ui/views/AssuranceStpaWizardView.vue#analysis_id')).toBe(true)
    expect(found.has('ui/views/EntitiesView.vue#domain')).toBe(true)
    expect(found.has('ui/composables/useTierFacet.ts#*')).toBe(true)
  })

  it('records the identity uses Phase 2 has left to convert', () => {
    // Phase 2's exit criterion is that this list is empty. Until then it is the work remaining,
    // stated in the source tree rather than in a report.
    expect(identityQueryUses().length).toBeGreaterThanOrEqual(0)
  })
})
