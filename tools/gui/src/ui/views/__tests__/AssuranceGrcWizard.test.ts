import { describe, it, expect } from 'vitest'
import {
  GRC_STEPS,
  TREATMENT_OPTIONS,
  parseAttributes,
  riskTreatment,
  riskScore,
  summariseGrcComplete,
  grcStepBadges,
  gapNodeIds,
  linkedSourceIds,
  unlinkedSources,
  type AssuranceNode,
  type AssuranceEdge,
} from '../AssuranceGrcWizard.helpers'

describe('GRC_STEPS', () => {
  it('runs Risks → Treatment → Controls → Obligations → Coverage', () => {
    expect(GRC_STEPS.map((s) => s.key)).toEqual([
      'risks', 'treatment', 'controls', 'obligations', 'coverage',
    ])
  })

  it('offers the ISO 31000 treatment dispositions', () => {
    expect([...TREATMENT_OPTIONS]).toEqual(['mitigate', 'transfer', 'avoid', 'accept'])
  })
})

describe('parseAttributes', () => {
  it('parses a JSON attribute map', () => {
    const node: AssuranceNode = {
      node_id: 'RSK@1', node_type: 'risk', name: 'r',
      attributes_json: '{"treatment":"mitigate","likelihood":"high"}',
    }
    expect(parseAttributes(node)).toEqual({ treatment: 'mitigate', likelihood: 'high' })
  })

  it('returns an empty map for missing or malformed json', () => {
    expect(parseAttributes({ node_id: 'x', node_type: 'risk', name: 'r' })).toEqual({})
    expect(parseAttributes({ node_id: 'x', node_type: 'risk', name: 'r', attributes_json: '{' })).toEqual({})
  })
})

describe('riskTreatment / riskScore', () => {
  const node: AssuranceNode = {
    node_id: 'RSK@1', node_type: 'risk', name: 'r',
    attributes_json: '{"treatment":"accept","likelihood":"low","impact":"high"}',
  }

  it('reads the treatment disposition', () => {
    expect(riskTreatment(node)).toBe('accept')
    expect(riskTreatment({ node_id: 'x', node_type: 'risk', name: 'r' })).toBe('')
  })

  it('formats a likelihood × impact score', () => {
    expect(riskScore(node)).toBe('low × high')
    expect(riskScore({ node_id: 'x', node_type: 'risk', name: 'r' })).toBe('')
  })
})

describe('summariseGrcComplete', () => {
  it('extracts failed checks with gap counts', () => {
    const summary = summariseGrcComplete({
      passed: false,
      checks: {
        obligation_has_constraint: { passed: true, gap_count: 0 },
        risk_has_treatment: { passed: false, gap_count: 1 },
        risk_has_owner: { passed: false, gap_count: 2 },
      },
    })
    expect(summary.passed).toBe(false)
    expect(summary.failed).toEqual([
      { key: 'risk_has_treatment', gapCount: 1 },
      { key: 'risk_has_owner', gapCount: 2 },
    ])
  })
})

describe('gapNodeIds', () => {
  it('collects the node ids flagged by a named check', () => {
    const ids = gapNodeIds({
      passed: false,
      checks: {
        risk_has_owner: { passed: false, gap_count: 2, gaps: [
          { node_id: 'RSK@1', name: 'a' }, { node_id: 'RSK@2', name: 'b' },
        ] },
      },
    }, 'risk_has_owner')
    expect(ids).toEqual(new Set(['RSK@1', 'RSK@2']))
  })

  it('returns an empty set for a passing or absent check', () => {
    expect(gapNodeIds(null, 'risk_has_owner').size).toBe(0)
    expect(gapNodeIds({ passed: true, checks: {} }, 'risk_has_owner').size).toBe(0)
  })
})

describe('grcStepBadges', () => {
  it('flags steps once their content exists', () => {
    const keys = grcStepBadges([
      { node_id: 'RSK@1', node_type: 'risk', name: 'r', attributes_json: '{"treatment":"mitigate"}' },
      { node_id: 'ACN@1', node_type: 'assurance-constraint', name: 'c' },
    ])
    expect(keys.has('risks')).toBe(true)
    expect(keys.has('treatment')).toBe(true)
    expect(keys.has('controls')).toBe(true)
    expect(keys.has('obligations')).toBe(false)
  })

  it('does not flag treatment when no risk has a treatment set', () => {
    const keys = grcStepBadges([{ node_id: 'RSK@1', node_type: 'risk', name: 'r' }])
    expect(keys.has('risks')).toBe(true)
    expect(keys.has('treatment')).toBe(false)
  })
})

describe('linkedSourceIds / unlinkedSources', () => {
  const risks: AssuranceNode[] = [
    { node_id: 'RSK@1', node_type: 'risk', name: 'a' },
    { node_id: 'RSK@2', node_type: 'risk', name: 'b' },
  ]
  const edges: AssuranceEdge[] = [
    { source_id: 'RSK@1', target_id: 'ACN@1', conn_type: 'treated-by' },
    { source_id: 'RSK@2', target_id: 'ACN@1', conn_type: 'other' },
  ]

  it('finds sources already linked to a target via a conn type', () => {
    expect(linkedSourceIds(edges, 'ACN@1', 'treated-by')).toEqual(new Set(['RSK@1']))
  })

  it('returns only the not-yet-linked sources', () => {
    expect(unlinkedSources(risks, edges, 'ACN@1', 'treated-by').map((r) => r.node_id))
      .toEqual(['RSK@2'])
  })
})
