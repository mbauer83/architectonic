import { describe, expect, it } from 'vitest'
import { Effect } from 'effect'
import type { CandidateSummary } from '../../domain/schemas/candidates'
import type { CandidateAccess } from './useCandidates'
import { useCandidateCatalog } from './useCandidateCatalog'

const candidate = (id: string, parent: string | null = null, scope: readonly string[] = []): CandidateSummary =>
  ({ id, name: `${id} name`, state: 'draft', parent, scope, diagram: null, operations: 0 })

const fakeAccess = (store: CandidateSummary[], reads: string[] = []): CandidateAccess => ({
  listCandidates: () => Effect.succeed([...store]),
  createCandidate: () => {
    store.push(candidate('empty'))
    return Effect.succeed({ record: { id: 'empty' }, version: 'v1' })
  },
  readCandidate: (id) => {
    reads.push(id)
    return Effect.die('the list carries what the catalogue shows')
  },
  rebaseCandidate: () => Effect.die('not used'),
  compareCandidate: () => Effect.die('not used'),
  deleteCandidate: (id) => {
    store.splice(store.findIndex((one) => one.id === id), 1)
    return Effect.succeed(undefined)
  },
  editCandidate: () => Effect.die('not used'),
})

describe('useCandidateCatalog', () => {
  it('groups every candidate by its root\'s scope from the list read alone', async () => {
    const reads: string[] = []
    const catalog = useCandidateCatalog(fakeAccess(
      [candidate('naive', null, ['e1', 'e2']), candidate('queue', 'naive'), candidate('lost')], reads))
    await catalog.refresh()
    expect(catalog.groups.value.map((group) => group.rows.map((row) => row.candidate.id)))
      .toEqual([['lost'], ['naive', 'queue']])
    expect(reads).toEqual([])
  })

  it('lists again after a create and a delete', async () => {
    const catalog = useCandidateCatalog(fakeAccess([candidate('naive')]))
    await catalog.refresh()
    expect(await catalog.create({ name: 'Empty' })).toBe('empty')
    expect(catalog.candidates.all.value.map((one) => one.id)).toContain('empty')
    expect(await catalog.remove('empty')).toBe(true)
    expect(catalog.candidates.all.value.map((one) => one.id)).not.toContain('empty')
  })
})
