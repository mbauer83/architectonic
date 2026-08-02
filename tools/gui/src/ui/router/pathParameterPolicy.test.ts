import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { describe, expect, it } from 'vitest'
import { ROUTE_TEMPLATES } from './artifactRoutes'

/**
 * Every `route.params.<name>` a view reads must be a name some route template declares.
 *
 * 0.2.0 moved identity into the path, and the parameter names moved with it. `AssuranceNodeView`
 * kept reading `route.params.id` after its template became `/assurance/nodes/:nodeId`, so the id
 * resolved to `''` on every deep link: the page rendered an empty detail frame for a node that
 * exists, said nothing was wrong, and every gate stayed green — a missing parameter is `undefined`,
 * not a type error, and nothing else in the program mentions the name.
 *
 * The check is deliberately over the whole declared vocabulary rather than per-view: tying a `.vue`
 * file to its own route means parsing the component loaders in the route table, and a check that
 * silently stops resolving them would pass while scanning nothing. A name no template declares
 * cannot be right for any view, and that is enough to catch the whole class.
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

const withoutComments = (line: string): string => {
  const trimmed = line.trimStart()
  if (trimmed.startsWith('//') || trimmed.startsWith('*') || trimmed.startsWith('/*')) return ''
  const comment = line.indexOf('//')
  return comment === -1 ? line : line.slice(0, comment)
}

const PARAM_READ = /route\.params(?:\.([A-Za-z_$][\w$]*)|\[\s*'([^']+)'\s*\]|\[\s*"([^"]+)"\s*\])/g

/** `<relative path>#<name>` for every path-parameter read in the tree. */
const parameterReads = (): Set<string> => {
  const reads = new Set<string>()
  for (const file of sourceFiles(SRC_ROOT)) {
    const relativePath = relative(SRC_ROOT, file).split('\\').join('/')
    for (const rawLine of readFileSync(file, 'utf8').split('\n')) {
      for (const match of withoutComments(rawLine).matchAll(PARAM_READ)) {
        reads.add(`${relativePath}#${match[1] ?? match[2] ?? match[3]}`)
      }
    }
  }
  return reads
}

const declaredNames = (): Set<string> =>
  new Set(
    Object.values(ROUTE_TEMPLATES).flatMap((template) =>
      [...template.matchAll(/:([A-Za-z_$][\w$]*)/g)].map((match) => match[1]),
    ),
  )

describe('path parameter policy', () => {
  it('finds the reads it is meant to check', () => {
    // A scanner that stops finding anything passes. This is the guard against that.
    expect(parameterReads().size).toBeGreaterThan(10)
  })

  it('every declared template contributes at least one parameter name', () => {
    expect(declaredNames().size).toBeGreaterThan(3)
  })

  it('reads only parameter names a route template declares', () => {
    const declared = declaredNames()
    const undeclared = [...parameterReads()]
      .filter((read) => !declared.has(read.split('#')[1]))
      .sort()

    expect(undeclared, `no route template declares these path parameters:\n  ${undeclared.join('\n  ')}`)
      .toEqual([])
  })
})
