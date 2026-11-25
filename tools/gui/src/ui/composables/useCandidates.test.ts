import { describe, expect, it } from 'vitest'
import { shallowRef } from 'vue'
import { Effect } from 'effect'
import { NetworkError } from '../../domain/errors'
import type { CandidateComparison, CandidateSummary } from '../../domain/schemas/candidates'
import { type CandidateAccess, useCandidates } from './useCandidates'

const candidate = (id: string, parent: string | null = null): CandidateSummary =>
  ({ id, name: `${id} name`, state: 'draft', parent, scope: [], diagram: null, operations: 0 })

const comparisonOf = (id: string, base: string): CandidateComparison =>
  ({ candidate: id, base, standing: [], stack: [], view: { entities: [], connections: [] }, diff: [] })

/** An in-memory candidate store that records what was asked of it. */
const fakeAccess = (initial: CandidateSummary[], refuseDelete = false) => {
  const store = [...initial]
  const calls: string[] = []
  const access: CandidateAccess = {
    listCandidates: () => Effect.succeed([...store]),
    createCandidate: (record) => {
      const id = `new-${store.length}`
      calls.push(`create ${JSON.stringify(record)}`)
      store.push(candidate(id, typeof record.parent === 'string' ? record.parent : null))
      return Effect.succeed({ record: { id, ...record }, version: 'v1' })
    },
    readCandidate: (id) => Effect.succeed({ record: { id }, version: `v-${id}` }),
    rebaseCandidate: (id, basedOn) => {
      calls.push(`rebase ${id} ${basedOn}`)
      return Effect.succeed({ record: { id }, version: 'v2' })
    },
    compareCandidate: (id, base, diagram) => {
      calls.push(`compare ${id} ${base} ${diagram ?? '-'}`)
      return Effect.succeed(comparisonOf(id, base))
    },
    deleteCandidate: (id) => {
      if (refuseDelete) return Effect.fail(new NetworkError({ status: 409, message: `${id} cannot be deleted` }))
      store.splice(store.findIndex((one) => one.id === id), 1)
      calls.push(`delete ${id}`)
      return Effect.succeed(undefined)
    },
    editCandidate: (id, basedOn, patch) => {
      calls.push(`edit ${id} ${basedOn} ${JSON.stringify(patch)}`)
      const at = store.findIndex((one) => one.id === id)
      if (at >= 0 && typeof patch.state === 'string') store[at] = { ...store[at]!, state: patch.state }
      return Effect.succeed({ record: { id, ...patch }, version: 'v3' })
    },
  }
  return { access, calls }
}

// naive ← queue ← bounded; elsewhere stands alone.
const ALL = [candidate('naive'), candidate('queue', 'naive'), candidate('bounded', 'queue'), candidate('elsewhere')]

describe('useCandidates', () => {
  it('reads a root supplied by its caller, as a stress analysis supplies its naive architecture', async () => {
    const { access, calls } = fakeAccess(ALL)
    const candidates = useCandidates(access, { root: () => 'naive', scopeDiagram: () => 'DIA-1' })
    await candidates.load()
    expect(candidates.inStack.value.map((one) => one.id)).toEqual(['naive', 'queue', 'bounded'])
    await candidates.select('queue')
    expect(candidates.against.value).toBe('naive')
    expect(calls).toEqual(['compare queue naive DIA-1'])
    expect(candidates.comparison.value?.candidate).toBe('queue')
  })

  it('reads, with no root supplied, the stack the selected candidate stands in', async () => {
    const { access, calls } = fakeAccess(ALL)
    const candidates = useCandidates(access, { scopeDiagram: () => '' })
    await candidates.load()
    expect(candidates.inStack.value).toEqual([])
    await candidates.select('bounded')
    expect(candidates.root.value).toBe('naive')
    expect(candidates.choices.value.map((one) => one.value)).toEqual(['model', 'naive', 'queue'])
    await candidates.compareWith('model')
    expect(calls).toEqual(['compare bounded queue -', 'compare bounded model -'])
  })

  it('reads a candidate against a base its caller chooses, over a list shared with other readings', async () => {
    const { access, calls } = fakeAccess(ALL)
    const all = shallowRef<readonly CandidateSummary[]>([])
    const one = useCandidates(access, { scopeDiagram: () => '', all })
    const other = useCandidates(access, { scopeDiagram: () => '', all })
    await one.load()
    expect(other.all.value.map((each) => each.id)).toContain('bounded')
    await other.select('bounded', 'naive')
    expect(other.against.value).toBe('naive')
    expect(calls).toEqual(['compare bounded naive -'])
  })

  it('keeps no comparison read against a base it has since moved away from', async () => {
    const { access } = fakeAccess(ALL)
    const candidates = useCandidates(access, { scopeDiagram: () => '' })
    await candidates.load()
    const first = candidates.select('bounded', 'naive')
    candidates.against.value = 'model'
    await first
    expect(candidates.comparison.value).toBeNull()
  })

  it('creates a candidate from a diagram, and stacks one on another and reads it', async () => {
    const { access, calls } = fakeAccess(ALL)
    const candidates = useCandidates(access, { scopeDiagram: () => '' })
    await candidates.load()
    const scoped = await candidates.create({ name: 'From a diagram', diagram: 'DIA-2' })
    expect(scoped).toBe('new-4')
    expect(candidates.all.value.some((one) => one.id === 'new-4')).toBe(true)
    const stacked = await candidates.stackOn('bounded', 'On top')
    expect(candidates.selected.value).toBe(stacked)
    expect(candidates.against.value).toBe('bounded')
    expect(calls.slice(0, 2)).toEqual([
      'create {"name":"From a diagram","diagram":"DIA-2"}', 'create {"name":"On top","parent":"bounded"}',
    ])
  })

  it('re-bases a candidate on the version it reads, then reads it again', async () => {
    const { access, calls } = fakeAccess(ALL)
    const candidates = useCandidates(access, { scopeDiagram: () => '' })
    await candidates.load()
    await candidates.select('queue')
    expect(await candidates.rebase('queue')).toBe(true)
    expect(calls).toEqual(['compare queue naive -', 'rebase queue v-queue', 'compare queue naive -'])
  })

  it('deletes a candidate, forgetting it as the one being read', async () => {
    const { access } = fakeAccess(ALL)
    const candidates = useCandidates(access, { scopeDiagram: () => '' })
    await candidates.load()
    await candidates.select('elsewhere')
    expect(await candidates.remove('elsewhere')).toBe(true)
    expect(candidates.selected.value).toBeNull()
    expect(candidates.comparison.value).toBeNull()
    expect(candidates.all.value.map((one) => one.id)).not.toContain('elsewhere')
  })

  it('says why a delete was refused, and keeps the candidate', async () => {
    const { access } = fakeAccess(ALL, true)
    const candidates = useCandidates(access, { scopeDiagram: () => '' })
    await candidates.load()
    expect(await candidates.remove('naive')).toBe(false)
    expect(candidates.error.value).toContain('naive cannot be deleted')
    expect(candidates.all.value.map((one) => one.id)).toContain('naive')
  })

  it('rejects a candidate through its versioned edit, keeping it listed as rejected', async () => {
    const { access, calls } = fakeAccess(ALL)
    const candidates = useCandidates(access, { scopeDiagram: () => '' })
    await candidates.load()
    expect(await candidates.reject('elsewhere')).toBe(true)
    expect(calls).toContain('edit elsewhere v-elsewhere {"state":"rejected"}')
    expect(candidates.all.value.find((one) => one.id === 'elsewhere')?.state).toBe('rejected')
  })
})
