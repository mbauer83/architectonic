import { describe, expect, it } from 'vitest'
import { mkQuery } from './viewpointCriteria'
import { queryFromMapping, queryToMapping } from './viewpointCriteriaSerialization'
import { type TracePatternNode } from './viewpointTracePattern'
import { tracePatternFromMapping, tracePatternToMapping } from './viewpointTracePatternSerialization'

// The exact §10.4 shipped `motivation-coverage` shape, in wire form — the fidelity anchor.
const MOTIVATION_MAPPING = {
  name: 'motivation',
  kind: 'branch-complete-realization',
  applies_to: ['goal', 'outcome'],
  branches: {
    goal_to_outcome: { kind: 'stored-edge', connection: 'archimate-realization', direction: 'incoming', endpoint: { type: 'outcome' } },
    outcome_to_requirement: { kind: 'stored-edge', connection: 'archimate-realization', direction: 'incoming', endpoint: { type: 'requirement' } },
  },
  shortcuts: [
    { kind: 'diagnostic-edge', connection: 'archimate-influence', direction: 'incoming', endpoint: { type: 'requirement' }, status: 'shortcut' },
    { kind: 'diagnostic-edge', connection: 'archimate-association', direction: 'incoming', endpoint: { type: 'requirement' }, status: 'ambiguous_link' },
  ],
  leaf: { kind: 'none' },
}

const OVERALL_MAPPING = {
  name: 'overall_realization',
  kind: 'branch-complete-realization',
  applies_to: ['goal', 'outcome', 'requirement'],
  branches: { ref: 'motivation' },
  leaf: {
    kind: 'derived-reachability',
    connection: 'archimate-realization',
    traversal: 'direct_and_derived',
    max_hops: 4,
    endpoint: { registry: 'permitted-realizers-of-requirement' },
  },
}

const DIAGNOSTIC_LAYER_MAPPING = {
  name: 'behavior_coverage',
  kind: 'branch-complete-realization',
  applies_to: ['goal', 'outcome', 'requirement'],
  branches: { ref: 'motivation' },
  leaf: {
    kind: 'derived-reachability',
    connection: 'archimate-realization',
    traversal: 'direct_and_derived',
    max_hops: 4,
    endpoint: { domain: 'behavior', class: 'behavior-element' },
  },
  diagnostic: true,
}

const roundTrip = (mapping: Record<string, unknown>) => tracePatternToMapping(tracePatternFromMapping(mapping))

describe('trace pattern serialization', () => {
  it('round-trips the inline-branch motivation pattern with shortcuts and a none leaf', () => {
    expect(roundTrip(MOTIVATION_MAPPING)).toEqual(MOTIVATION_MAPPING)
  })

  it('round-trips a {ref} branches pattern with a registry derived-reachability leaf', () => {
    expect(roundTrip(OVERALL_MAPPING)).toEqual(OVERALL_MAPPING)
  })

  it('preserves the diagnostic flag and a layer-membership leaf', () => {
    expect(roundTrip(DIAGNOSTIC_LAYER_MAPPING)).toEqual(DIAGNOSTIC_LAYER_MAPPING)
  })

  it('omits an empty shortcuts list and never emits a diagnostic flag when false', () => {
    const pattern = tracePatternFromMapping(OVERALL_MAPPING)
    const mapping = tracePatternToMapping(pattern)
    expect('shortcuts' in mapping).toBe(false)
    expect('diagnostic' in mapping).toBe(false)
  })

  it('parses a {ref} branch as a ref node, not inline edges', () => {
    const pattern: TracePatternNode = tracePatternFromMapping(OVERALL_MAPPING)
    expect(pattern.branches.kind).toBe('ref')
    if (pattern.branches.kind === 'ref') expect(pattern.branches.ref).toBe('motivation')
  })

  it('drops a layer leaf class key when absent', () => {
    const noClass = { ...DIAGNOSTIC_LAYER_MAPPING, leaf: { ...DIAGNOSTIC_LAYER_MAPPING.leaf, endpoint: { domain: 'behavior' } } }
    expect(roundTrip(noClass)).toEqual(noClass)
  })
})

describe('trace patterns on the query', () => {
  it('serializes trace_patterns onto the query mapping and reads them back', () => {
    const query = mkQuery()
    query.tracePatterns = [tracePatternFromMapping(MOTIVATION_MAPPING), tracePatternFromMapping(OVERALL_MAPPING)]
    const mapping = queryToMapping(query)
    expect(mapping.trace_patterns).toEqual([MOTIVATION_MAPPING, OVERALL_MAPPING])
    expect(queryFromMapping(mapping).tracePatterns.map(tracePatternToMapping)).toEqual([MOTIVATION_MAPPING, OVERALL_MAPPING])
  })

  it('omits trace_patterns entirely when there are none (existing round-trips unaffected)', () => {
    expect('trace_patterns' in queryToMapping(mkQuery())).toBe(false)
  })
})
