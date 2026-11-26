import { describe, expect, it } from 'vitest'
import type { DocumentTableRow } from '../schemas/candidates'
import type { AnalysisEvaluation, ArchitectureStanding } from '../schemas/stressEvaluation'
import {
  architectureName, heldApartIds, judgement, procedure, residualityDetail, residualityLine, signed, verdictRow,
} from './testSet'

const row = (row_id: string, values: Record<string, string | boolean>): DocumentTableRow =>
  ({ row_id, values, unreadable: {} })

const emptyEvaluation: AnalysisEvaluation = {
  document: 'STA@1.a', naive_candidate: '', design_stressors: 0, stressors: [], verdicts: [],
  unwritten_perspectives: [], architectures: [],
  stage: { naive_judged: false, adapted: false, integrated: false, integration_judged: false },
}

const standing = (overrides: Partial<ArchitectureStanding>): ArchitectureStanding => ({
  architecture: 'CAND@1', integrated: false, usable: 12, judged: 12, survives: 8, degrades: 0, fails: 4,
  naive_survives: 4, ...overrides,
})

describe('the residuality line', () => {
  it('says the figure, the survivals and the naive’s, as the owner wrote it', () => {
    expect(residualityLine(standing({ residuality: 1 / 3 }))).toBe('Residuality +0.33 · survives 8 of 12 (naive 4)')
  })

  it('says how many are judged while some are not, and gives no figure', () => {
    expect(residualityLine(standing({ judged: 5 }))).toBe('5 of 12 judged')
  })

  it('reads the naive by its survivals alone', () => {
    expect(residualityLine(standing({ architecture: 'naive', survives: 4 }))).toBe('survives 4 of 12')
    expect(residualityLine(standing({ architecture: 'naive', judged: 3 }))).toBe('3 of 12 judged')
  })

  it('puts the strict figure and the degraded verdicts on hover', () => {
    const detail = residualityDetail(standing({ residuality: 0.25, strict: 0.17, survives: 6, degrades: 2 }))
    expect(detail).toContain('Strict +0.17, counting full survivals only.')
    expect(detail).toContain('degrades 2')
  })

  it('signs a figure the way a reader expects', () => {
    expect([signed(0.333), signed(-0.08), signed(0)]).toEqual(['+0.33', '−0.08', '±0.00'])
  })
})

describe('a judgement', () => {
  const verdicts = [
    row('T1', { stressor: 'S2', architecture: 'naive', verdict: 'fails' }),
    row('T2', { stressor: 'S2', architecture: 'CAND@1', verdict: 'fails' }),
    row('T3', { stressor: 'S2', architecture: 'CAND@1', verdict: 'survives' }),
  ]

  it('changes the architecture’s latest row on the stressor', () => {
    const found = verdictRow(verdicts, 'S2', 'CAND@1')
    expect(found?.row_id).toBe('T3')
    expect(judgement(found, 'S2', 'CAND@1', { verdict: 'degrades' })).toEqual({
      op: 'change', row_id: 'T3', based_on: found?.values, cells: { verdict: 'degrades' },
    })
  })

  it('finds a verdict written with the short id of the candidate it judges', () => {
    // Regression: a row written over MCP with `CAND@….random` was never the one a judgement changed.
    const short = [row('T1', { stressor: 'S2', architecture: 'CAND@1795689702.C6UOgl5', verdict: 'fails' })]
    expect(verdictRow(short, 'S2', 'CAND@1795689702.C6UOgl5.adaptation-local-text-reader')?.row_id).toBe('T1')
    expect(verdictRow(short, 'S2', 'naive')).toBeUndefined()
  })

  it('adds a usable row where the architecture has none', () => {
    expect(judgement(verdictRow(verdicts, 'S3', 'naive'), 'S3', 'naive', { verdict: 'survives' })).toEqual({
      op: 'add', cells: { stressor: 'S3', architecture: 'naive', usable: true, verdict: 'survives' },
    })
  })
})

describe('the test set and its procedure', () => {
  it('holds apart exactly the stressors the evaluation reads as the test set', () => {
    const stressors = [{ id: 'S1', stressor: 'Flood', usable: true }, { id: 'S4', stressor: 'Fire', usable: false }]
    expect([...heldApartIds({ ...emptyEvaluation, stressors })]).toEqual(['S1', 'S4'])
    expect(heldApartIds(null).size).toBe(0)
  })

  it('shows the order as progress, each step done or not', () => {
    const steps = procedure({ naive_judged: true, adapted: true, integrated: false, integration_judged: false })
    expect(steps.map((step) => [step.label, step.done])).toEqual([
      ['Judge the naive', true], ['Adapt', true], ['Integrate', false], ['Judge the integration', false],
    ])
  })
})

describe('an architecture judged against the test set', () => {
  const NAMES: Readonly<Record<string, string>> = { 'CAND@1': 'Bounded queues', 'CAND@2': 'Second reviewer' }
  const names = (id: string): string => NAMES[id] ?? id
  it('is the naive, a candidate by its name, or the integration of what was integrated apart', () => {
    const standings = [
      standing({ architecture: 'naive' }), standing({ architecture: 'CAND@1', integrated: true }),
      standing({ architecture: 'CAND@2', integrated: true }), standing({ architecture: 'CAND@3' }),
    ]
    expect(['naive', 'CAND@1', 'integration'].map((one) => architectureName(one, standings, names)))
      .toEqual(['Naive architecture', 'Bounded queues', 'The integration of Bounded queues and Second reviewer'])
  })
})
