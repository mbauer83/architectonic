import { describe, expect, it } from 'vitest'
import { Effect } from 'effect'
import { NetworkError } from '../../domain/errors'
import type { CandidateSummary } from '../../domain/schemas/candidates'
import type { CandidateAccess } from './useCandidates'
import { useCandidateCatalog } from './useCandidateCatalog'

const candidate = (id: string, parent: string | null = null): CandidateSummary =>
  ({ id, name: `${id} name`, state: 'draft', parent })

const RECORDS: Record<string, Record<string, unknown>> = {
  naive: { id: 'naive', scope: ['e1', 'e2'], changes: { operations: [{}, {}] } },
  queue: { id: 'queue', parent: 'naive', changes: { operations: [{}] } },
}

const fakeAccess = (store: CandidateSummary[]): CandidateAccess => ({
  listCandidates: () => Effect.succeed([...store]),
  createCandidate: (record) => {
    store.push(candidate('empty'))
    RECORDS.empty = { id: 'empty', ...record, changes: { operations: [] } }
    return Effect.succeed({ record: RECORDS.empty, version: 'v1' })
  },
  readCandidate: (id) => {
    const record = RECORDS[id]
    return record
      ? Effect.succeed({ record, version: 'v1' })
      : Effect.fail(new NetworkError({ status: 404, message: `${id} not found` }))
  },
  rebaseCandidate: () => Effect.die('not used'),
  compareCandidate: () => Effect.die('not used'),
  deleteCandidate: (id) => {
    store.splice(store.findIndex((one) => one.id === id), 1)
    return Effect.succeed(undefined)
  },
})

describe('useCandidateCatalog', () => {
  it('lists every candidate with what its record says, grouped by its root\'s scope', async () => {
    const catalog = useCandidateCatalog(fakeAccess([candidate('naive'), candidate('queue', 'naive'), candidate('lost')]))
    await catalog.refresh()
    expect(catalog.facts.value.get('naive')).toEqual({ scope: ['e1', 'e2'], operations: 2 })
    expect(catalog.facts.value.get('queue')).toEqual({ scope: [], operations: 1 })
    // A record that cannot be read leaves its candidate listed, without facts.
    expect(catalog.facts.value.has('lost')).toBe(false)
    expect(catalog.groups.value.map((group) => group.rows.map((row) => row.candidate.id)))
      .toEqual([['lost'], ['naive', 'queue']])
  })

  it('reads the facts again after a create and a delete', async () => {
    const catalog = useCandidateCatalog(fakeAccess([candidate('naive')]))
    await catalog.refresh()
    expect(await catalog.create({ name: 'Empty' })).toBe('empty')
    expect(catalog.facts.value.get('empty')).toEqual({ scope: [], operations: 0 })
    expect(await catalog.remove('empty')).toBe(true)
    expect(catalog.facts.value.has('empty')).toBe(false)
  })
})
