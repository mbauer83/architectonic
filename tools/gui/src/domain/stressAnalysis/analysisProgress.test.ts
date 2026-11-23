import { describe, expect, it } from 'vitest'
import type { AnalysisProgress } from '../schemas/candidates'
import { coverageHints, whatIsLeft } from './analysisProgress'

const progress = (overrides: Partial<AnalysisProgress['progress']> = {}, untouched: AnalysisProgress['coverage']['untouched'] = []): AnalysisProgress => ({
  document: 'STRESS@1', naive_candidate: 'CAND@1',
  progress: {
    unwalked: [], without_end_state: [], without_required_behaviour: [], without_adaptation: [],
    unexplained_hits: [], incomplete_rows: [], ...overrides,
  },
  coverage: { by_kind: { scale: 1 }, unused_kinds: ['time'], single_stressor_end_states: ['E1'], untouched },
})

describe('what is left', () => {
  it('says each gap as a sentence about a row, on the tab that holds it', () => {
    const left = whatIsLeft(progress({
      unwalked: ['S1'], without_end_state: ['S2'], without_adaptation: ['E1'],
      incomplete_rows: [{ table: 'adaptations', row: 'A1', column: 'candidate_architecture' }],
    }).progress)
    expect(left.map(({ tab, row, text }) => [tab, row, text])).toEqual([
      ['stressors', 'S1', 'S1: what happens is not written.'],
      ['stressors', 'S2', 'S2 leads to no end state yet.'],
      ['end-states', 'E1', 'E1 has no adaptation and no reason for none.'],
      ['adaptations', 'A1', 'A1: candidate architecture is missing or unreadable.'],
    ])
    expect(new Set(left.map((item) => item.key)).size).toBe(left.length)
  })

  it('is empty when nothing is', () => {
    expect(whatIsLeft(progress().progress)).toEqual([])
  })
})

describe('coverage hints', () => {
  it('puts well-connected untouched elements apart from the rest, and names them', () => {
    const hints = coverageHints(progress({ without_end_state: ['S3'] }, [
      { id: 'A', fan_in: 4, fan_out: 2 }, { id: 'B', fan_in: 1, fan_out: 2 },
      { id: 'C', fan_in: 1, fan_out: 0 }, { id: 'D', fan_in: 0, fan_out: 0 },
    ]), (id) => `${id} name`)
    expect(hints.wellConnected.map((one) => [one.name, one.relations])).toEqual([['A name', 6], ['B name', 3]])
    expect(hints.otherUntouched.map((one) => one.id)).toEqual(['C', 'D'])
    expect(hints.unusedKinds).toEqual(['time'])
    expect(hints.singleStressorEndStates).toEqual(['E1'])
    expect(hints.withoutEndState).toEqual(['S3'])
  })

  it('counts the top quarter as well connected when nothing has three relations', () => {
    const hints = coverageHints(progress({}, [
      { id: 'A', fan_in: 1, fan_out: 1 }, { id: 'B', fan_in: 1, fan_out: 0 },
      { id: 'C', fan_in: 1, fan_out: 0 }, { id: 'D', fan_in: 0, fan_out: 0 },
    ]), (id) => id)
    expect(hints.wellConnected.map((one) => one.id)).toEqual(['A'])
  })
})
