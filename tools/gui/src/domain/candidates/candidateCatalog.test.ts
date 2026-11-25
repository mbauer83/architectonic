import { describe, expect, it } from 'vitest'
import type { CandidateSummary } from '../schemas/candidates'
import { catalogOf, scopeLabel } from './candidateCatalog'

const SCOPES: Record<string, readonly string[]> = { naive: ['e1', 'e2'], other: ['e2', 'e1'] }
const candidate = (id: string, parent: string | null = null): CandidateSummary =>
  ({ id, name: `${id} name`, state: 'draft', parent, scope: SCOPES[id] ?? [], diagram: null, operations: 0 })

describe('the candidate catalogue', () => {
  // naive ← queue ← bounded; naive ← drift; other stands alone over the same scope; empty has none.
  const ALL = [
    candidate('bounded', 'queue'), candidate('queue', 'naive'), candidate('naive'), candidate('drift', 'naive'),
    candidate('other'), candidate('empty'),
  ]

  it('groups stacks by their root\'s scope and lists each candidate below what it stacks on', () => {
    const groups = catalogOf(ALL)
    expect(groups.map((group) => group.scope)).toEqual([[], ['e1', 'e2']])
    expect(groups[1]?.rows.map((row) => [row.candidate.id, row.depth])).toEqual([
      ['naive', 0], ['drift', 1], ['queue', 1], ['bounded', 2], ['other', 0],
    ])
  })

  it('treats a candidate whose parent is not listed as a root', () => {
    const rows = catalogOf([candidate('orphan', 'gone')]).flatMap((group) => group.rows)
    expect(rows.map((row) => [row.candidate.id, row.depth])).toEqual([['orphan', 0]])
  })

  it('lists each candidate of a cycle once', () => {
    const rows = catalogOf([candidate('a', 'b'), candidate('b', 'a')]).flatMap((group) => group.rows)
    expect(rows.map((row) => [row.candidate.id, row.depth])).toEqual([['a', 0], ['b', 1]])
  })

  it('heads a group with its scope', () => {
    expect(scopeLabel(['e1'])).toBe('Scope of 1 element')
    expect(scopeLabel(['e1', 'e2'])).toBe('Scope of 2 elements')
    expect(scopeLabel([])).toMatch(/^No scope/)
  })
})
