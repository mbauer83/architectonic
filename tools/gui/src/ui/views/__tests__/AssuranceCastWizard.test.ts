import { describe, it, expect } from 'vitest'
import {
  CAST_STEPS,
  summariseCastComplete,
  castStepBadges,
  gapNodeIds,
  linkedSourceIds,
  linkedTargetIds,
  unlinkedSources,
  type AssuranceNode,
  type AssuranceEdge,
} from '../AssuranceCastWizard.helpers'

describe('CAST_STEPS', () => {
  it('runs Baseline → Incident → Investigate → Corrective Actions → Review', () => {
    expect(CAST_STEPS.map((s) => s.key)).toEqual([
      'baseline', 'incident', 'investigate', 'corrective', 'review',
    ])
  })

  it('creates incidents and observed factors in the right steps', () => {
    expect(CAST_STEPS.find((s) => s.key === 'incident')?.nodeType).toBe('incident')
    expect(CAST_STEPS.find((s) => s.key === 'investigate')?.nodeType).toBe('control-structure-node')
    expect(CAST_STEPS.find((s) => s.key === 'corrective')?.nodeType).toBe('corrective-action')
  })
})

describe('summariseCastComplete', () => {
  it('extracts failed checks with gap counts', () => {
    const summary = summariseCastComplete({
      passed: false,
      checks: {
        baseline_exists: { passed: false, gap_count: 1 },
        incident_has_investigates: { passed: true, gap_count: 0 },
        corrective_action_derives_constraint: { passed: false, gap_count: 2 },
      },
    })
    expect(summary.passed).toBe(false)
    expect(summary.failed).toEqual([
      { key: 'baseline_exists', gapCount: 1 },
      { key: 'corrective_action_derives_constraint', gapCount: 2 },
    ])
  })
})

describe('gapNodeIds', () => {
  it('collects node ids flagged by a named check', () => {
    const ids = gapNodeIds({
      passed: false,
      checks: {
        incident_has_investigates: { passed: false, gap_count: 1, gaps: [{ node_id: 'INC@1', name: 'x' }] },
      },
    }, 'incident_has_investigates')
    expect(ids).toEqual(new Set(['INC@1']))
  })

  it('returns an empty set for null or a passing check', () => {
    expect(gapNodeIds(null, 'baseline_exists').size).toBe(0)
    expect(gapNodeIds({ passed: true, checks: {} }, 'baseline_exists').size).toBe(0)
  })
})

describe('castStepBadges', () => {
  it('flags baseline only when a baseline exists', () => {
    expect(castStepBadges([], 0).has('baseline')).toBe(false)
    expect(castStepBadges([], 1).has('baseline')).toBe(true)
  })

  it('flags content steps by node type', () => {
    const keys = castStepBadges([
      { node_id: 'INC@1', node_type: 'incident', name: 'i' },
      { node_id: 'CSN@1', node_type: 'control-structure-node', name: 'o' },
    ], 1)
    expect(keys.has('incident')).toBe(true)
    expect(keys.has('investigate')).toBe(true)
    expect(keys.has('corrective')).toBe(false)
  })
})

describe('link helpers', () => {
  const incidents: AssuranceNode[] = [
    { node_id: 'INC@1', node_type: 'incident', name: 'a' },
    { node_id: 'INC@2', node_type: 'incident', name: 'b' },
  ]
  const edges: AssuranceEdge[] = [
    { source_id: 'INC@1', target_id: 'CSN@1', conn_type: 'investigates' },
    { source_id: 'CRA@1', target_id: 'ACN@1', conn_type: 'derives' },
  ]

  it('finds incidents already investigating a target (source-centric)', () => {
    expect(linkedSourceIds(edges, 'CSN@1', 'investigates')).toEqual(new Set(['INC@1']))
  })

  it('returns not-yet-linked incidents for a target', () => {
    expect(unlinkedSources(incidents, edges, 'CSN@1', 'investigates').map((i) => i.node_id))
      .toEqual(['INC@2'])
  })

  it('finds constraints a corrective action derives (target-centric)', () => {
    expect(linkedTargetIds(edges, 'CRA@1', 'derives')).toEqual(new Set(['ACN@1']))
  })
})
