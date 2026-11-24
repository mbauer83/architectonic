import { describe, expect, it } from 'vitest'
import type { CandidateSummary } from '../schemas/candidates'
import type { CandidateFacts } from './candidateCatalog'
import { catalogOf, factsOf, scopeLabel } from './candidateCatalog'

const candidate = (id: string, parent: string | null = null): CandidateSummary =>
  ({ id, name: `${id} name`, state: 'draft', parent })
const facts = (scope: readonly string[], operations = 0): CandidateFacts => ({ scope, operations })

describe('a candidate read off its record', () => {
  it('names its scope and counts its operations', () => {
    expect(factsOf({ scope: ['b', 'a'], changes: { operations: [{}, {}, {}] } }))
      .toEqual({ scope: ['b', 'a'], operations: 3 })
  })

  it('reads nothing where the record states nothing', () => {
    expect(factsOf({ changes: {} })).toEqual({ scope: [], operations: 0 })
    expect(factsOf({ scope: 'not a list', changes: null })).toEqual({ scope: [], operations: 0 })
  })
})

describe('the candidate catalogue', () => {
  // naive ← queue ← bounded; naive ← drift; other stands alone over the same scope; empty has none.
  const ALL = [
    candidate('bounded', 'queue'), candidate('queue', 'naive'), candidate('naive'), candidate('drift', 'naive'),
    candidate('other'), candidate('empty'),
  ]
  const FACTS = new Map([['naive', facts(['e1', 'e2'])], ['other', facts(['e2', 'e1'])], ['empty', facts([])]])

  it('groups stacks by their root\'s scope and lists each candidate below what it stacks on', () => {
    const groups = catalogOf(ALL, FACTS)
    expect(groups.map((group) => group.scope)).toEqual([[], ['e1', 'e2']])
    expect(groups[1]?.rows.map((row) => [row.candidate.id, row.depth])).toEqual([
      ['naive', 0], ['drift', 1], ['queue', 1], ['bounded', 2], ['other', 0],
    ])
  })

  it('treats a candidate whose parent is not listed as a root', () => {
    const rows = catalogOf([candidate('orphan', 'gone')], new Map()).flatMap((group) => group.rows)
    expect(rows.map((row) => [row.candidate.id, row.depth])).toEqual([['orphan', 0]])
  })

  it('lists each candidate of a cycle once', () => {
    const rows = catalogOf([candidate('a', 'b'), candidate('b', 'a')], new Map()).flatMap((group) => group.rows)
    expect(rows.map((row) => [row.candidate.id, row.depth])).toEqual([['a', 0], ['b', 1]])
  })

  it('heads a group with its scope', () => {
    expect(scopeLabel(['e1'])).toBe('Scope of 1 element')
    expect(scopeLabel(['e1', 'e2'])).toBe('Scope of 2 elements')
    expect(scopeLabel([])).toMatch(/^No scope/)
  })
})
