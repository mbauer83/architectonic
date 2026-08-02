import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { describe, expect, it } from 'vitest'
import { assuranceRoutes } from './assuranceRoutes'
import { modelRoutes } from './modelRoutes'

/**
 * Every in-app address a view spells must be one this application serves.
 *
 * 0.2.0 moved identity into the path, and three links did not move with it: the browse list and
 * its row component pushed `/assurance/node/${id}` after the route became `/assurance/nodes/:nodeId`,
 * the node detail's "Explore graph" pushed `/assurance/graph?node_id=…` after the anchored surface
 * became `/assurance/nodes/:nodeId/graph`, and the FMEA wizard linked twice to the retired flat
 * `/assurance/fmea`. All three rendered a blank page — there was no not-found route either — and no
 * gate could see it: a string that matches no route is not a type error, and the unit suite mounts
 * components without a router.
 *
 * `artifactRoutes.layering.test.ts` is the sibling rule and answers a different question: whether a
 * layer *below* the delivery layer spells routes at all. Here the layer is allowed to spell them;
 * what is checked is that the address exists.
 *
 * Concatenation is the normal way an id reaches a path, so a literal ending in `/` is judged as a
 * prefix: `'/assurance/nodes/'` is live because a template continues it with a parameter, and
 * `'/assurance/node/'` is dead because none does.
 */

const SRC_ROOT = join(import.meta.dirname, '..', '..')
const UI_ROOT = join(SRC_ROOT, 'ui')

/** The router package itself declares the addresses; it is the authority, not a consumer. */
const ROUTER_DIR = join(UI_ROOT, 'router')

const isTestFile = (path: string): boolean =>
  path.endsWith('.test.ts') || path.endsWith('.test-d.ts') || path.includes(`${'__tests__'}/`)

const sourceFiles = (dir: string): string[] =>
  readdirSync(dir).flatMap((entry) => {
    const full = join(dir, entry)
    if (statSync(full).isDirectory()) return full === ROUTER_DIR ? [] : sourceFiles(full)
    if (!full.endsWith('.ts') && !full.endsWith('.vue')) return []
    return isTestFile(full) ? [] : [full]
  })

const withoutComments = (source: string): string =>
  source.replace(/\/\*[\s\S]*?\*\//g, '').replace(/(^|[^:])\/\/.*$/gm, '$1')

/** Segments of a served template, `:param` kept as the wildcard marker. */
const templateSegments = (): readonly (readonly string[])[] =>
  [...modelRoutes, ...assuranceRoutes]
    .map((route) => route.path.split('/').filter((segment) => segment.length > 0))

/**
 * The first segment of every served address — the vocabulary that makes a string an in-app
 * address rather than a repository path, a JSON pointer, or a CSS selector.
 */
const addressRoots = (): ReadonlySet<string> =>
  new Set(
    templateSegments()
      .map((segments) => segments[0])
      .filter((segment): segment is string => segment !== undefined && !segment.startsWith(':')),
  )

const STRING_LITERAL = /['"`](\/[A-Za-z][^'"`\n$]*)['"`]/g

interface Address { readonly file: string, readonly literal: string }

const addressesIn = (file: string): readonly Address[] => {
  const roots = addressRoots()
  const relativePath = relative(SRC_ROOT, file).split('\\').join('/')
  const found: Address[] = []
  for (const match of withoutComments(readFileSync(file, 'utf8')).matchAll(STRING_LITERAL)) {
    const literal = match[1]
    // `/api/...` is the backend's address space, not this router's.
    if (literal.startsWith('/api/') || literal.startsWith('/admin/')) continue
    const root = literal.split('?')[0].split('/')[1]
    if (root !== undefined && roots.has(root)) found.push({ file: relativePath, literal })
  }
  return found
}

/** Whether some served template matches the literal, treating a trailing `/` as "more follows". */
const isServed = (literal: string): boolean => {
  const path = literal.split('?')[0].split('#')[0]
  const open = path.endsWith('/')
  const segments = path.split('/').filter((segment) => segment.length > 0)
  return templateSegments().some((template) => {
    if (open ? template.length <= segments.length : template.length !== segments.length) return false
    return segments.every((segment, index) => {
      const expected = template[index]
      return expected !== undefined && (expected.startsWith(':') || expected === segment)
    })
  })
}

const allAddresses = (): readonly Address[] => sourceFiles(UI_ROOT).flatMap(addressesIn)

describe('in-app addresses name routes this application serves', () => {
  it('finds the addresses it is meant to check', () => {
    // A scanner that stops matching reports no offenders over an empty scan, and passes.
    expect(allAddresses().length).toBeGreaterThan(5)
    expect(addressRoots().size).toBeGreaterThan(5)
  })

  it('recognises a live address, a prefix awaiting an id, and a retired one', () => {
    expect(isServed('/assurance/nodes/x')).toBe(true)
    expect(isServed('/assurance/nodes/')).toBe(true)
    expect(isServed('/assurance/node/')).toBe(false)
    expect(isServed('/assurance/fmea')).toBe(false)
    expect(isServed('/entities')).toBe(true)
    expect(isServed('/viewpoints/some-slug/diagram')).toBe(true)
    expect(isServed('/viewpoints/diagram')).toBe(false)
  })

  it('every address spelled outside the router package is served', () => {
    const dead = allAddresses()
      .filter((address) => !isServed(address.literal))
      .map((address) => `${address.file}: ${address.literal}`)
      .sort()

    expect(dead, `these in-app links name no route:\n  ${dead.join('\n  ')}`).toEqual([])
  })
})
