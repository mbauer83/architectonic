import { describe, expect, it } from 'vitest'
import { ref } from 'vue'
import { Effect } from 'effect'
import { NetworkError } from '../../domain/errors'
import type { CandidateComparison, CandidateSummary, ChangeDifference } from '../../domain/schemas/candidates'
import { type ComparisonAccess, useCandidateComparison } from './useCandidateComparison'

const candidate = (id: string, parent: string | null = null): CandidateSummary =>
  ({ id, name: `${id} name`, state: 'candidate', parent, scope: [], diagram: null, operations: 1 })

const edited = (target: string): ChangeDifference =>
  ({ kind: 'entity', target, change: 'edited', fields: { name: { before: 'a', after: 'b' } } })

// naive ← queue ← bounded; naive ← queue ← retry; elsewhere stands alone.
const ALL = [
  candidate('naive'), candidate('queue', 'naive'), candidate('bounded', 'queue'), candidate('retry', 'queue'),
  candidate('elsewhere'),
]

const fakeAccess = (refuseCheck = false) => {
  const calls: string[] = []
  const access: ComparisonAccess = {
    listCandidates: () => Effect.succeed(ALL),
    createCandidate: () => Effect.die('not used'),
    readCandidate: () => Effect.die('not used'),
    rebaseCandidate: () => Effect.die('not used'),
    deleteCandidate: () => Effect.die('not used'),
    editCandidate: () => Effect.die('not used'),
    compareCandidate: (id, base, diagram) => {
      calls.push(`compare ${id} ${base} ${diagram ?? '-'}`)
      const comparison: CandidateComparison = {
        candidate: id, base, standing: [], stack: [], view: { entities: [], connections: [] },
        diff: [edited('ENT@1.x.db'), ...(id === 'bounded' ? [edited('ENT@2.y.api')] : [])],
      }
      return Effect.succeed(comparison)
    },
    checkCandidates: (ids) => {
      calls.push(`check ${ids.join(' ')}`)
      return refuseCheck
        ? Effect.fail(new NetworkError({ status: 400, message: 'Offer bounded as a candidate before checking integration.' }))
        : Effect.succeed({ candidates: [...ids], overlaps: [] })
    },
  }
  return { access, calls }
}

describe('useCandidateComparison', () => {
  it('reads every compared candidate against the nearest base they share, on the chosen diagram', async () => {
    const { access, calls } = fakeAccess()
    const ids = ref(['bounded', 'retry'])
    const comparison = useCandidateComparison(access, { ids: () => ids.value, base: () => '', diagram: () => 'DIA-1' })
    await comparison.load()
    await comparison.read()
    expect(comparison.base.value).toBe('queue')
    expect(comparison.choices.value.map((one) => one.value)).toEqual(['model', 'naive', 'queue'])
    expect([...calls].sort()).toEqual(['compare bounded queue DIA-1', 'compare retry queue DIA-1'])
    expect(comparison.panes.value.map((pane) => pane.reading.against.value)).toEqual(['queue', 'queue'])
  })

  it('reads against the base asked for only where every compared candidate shares it', async () => {
    const { access } = fakeAccess()
    const base = ref('naive')
    const ids = ref(['bounded', 'retry'])
    const comparison = useCandidateComparison(access, { ids: () => ids.value, base: () => base.value, diagram: () => '' })
    await comparison.load()
    expect(comparison.base.value).toBe('naive')
    ids.value = ['bounded', 'elsewhere']
    expect(comparison.base.value).toBe('model')
  })

  it('compares only the candidates it knows, and pairs what more than one of them changes', async () => {
    const { access } = fakeAccess()
    const comparison = useCandidateComparison(access, {
      ids: () => ['bounded', 'missing', 'retry'], base: () => '', diagram: () => '',
    })
    await comparison.load()
    await comparison.read()
    expect(comparison.known.value).toEqual(['bounded', 'retry'])
    expect([...(comparison.others.value.get('bounded')?.keys() ?? [])]).toEqual(['ENT@1.x'])
    expect(comparison.nameOf('retry')).toBe('retry name')
    expect(comparison.nameOf('missing')).toBe('missing')
  })

  it('keeps a pane reading the same candidate however often the comparison is read', async () => {
    const { access } = fakeAccess()
    const comparison = useCandidateComparison(access, { ids: () => ['bounded', 'retry'], base: () => '', diagram: () => '' })
    await comparison.load()
    const [first] = comparison.panes.value
    await comparison.read()
    expect(comparison.panes.value[0].reading).toBe(first.reading)
  })

  it('asks the server where the compared candidates overlap, and holds the answer for those candidates only', async () => {
    const { access, calls } = fakeAccess()
    const ids = ref(['bounded', 'retry'])
    const comparison = useCandidateComparison(access, { ids: () => ids.value, base: () => '', diagram: () => '' })
    await comparison.load()
    await comparison.runCheck()
    expect(calls).toContain('check bounded retry')
    expect(comparison.check.value?.overlaps).toEqual([])
    ids.value = ['bounded', 'elsewhere']
    expect(comparison.check.value).toBeNull()
  })

  it('says why the server refused the check', async () => {
    const { access } = fakeAccess(true)
    const comparison = useCandidateComparison(access, { ids: () => ['bounded', 'retry'], base: () => '', diagram: () => '' })
    await comparison.load()
    await comparison.runCheck()
    expect(comparison.check.value).toBeNull()
    expect(comparison.checkError.value).toContain('Offer bounded as a candidate')
    expect(comparison.checking.value).toBe(false)
  })

  it('says why the list could not be read', async () => {
    const { access } = fakeAccess()
    const failing: ComparisonAccess = {
      ...access, listCandidates: () => Effect.fail(new NetworkError({ status: 503, message: 'store unavailable' })),
    }
    const comparison = useCandidateComparison(failing, { ids: () => ['bounded'], base: () => '', diagram: () => '' })
    await comparison.load()
    expect(comparison.error.value).toContain('store unavailable')
  })
})
