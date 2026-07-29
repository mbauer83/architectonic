import { describe, expect, it } from 'vitest'
import { aggregationIneffective, buildAggregateView, isAggregateNodeId } from '../GraphExploreView.aggregate'
import type { AggregationSummary, ConnectionItemSummary, EntityItemSummary } from '../../../domain'

const entity = (id: string): EntityItemSummary => ({
  id, name: `Name ${id}`, type: 'application-component',
  specialization_slugs: [], group: 'uncategorized', domain: 'application', membership: 'primary',
  status: 'active', version: '1', column_values: null, anchor_modeled_distance: null, matched_via_derived_hops: null,
})

const connection = (id: string, source: string, target: string, certainty: 'certain' | 'potential' | null = null): ConnectionItemSummary => ({
  id, type: 'archimate-serving', source, target, certainty, hops: null, via_connection_ids: [], witness_steps: [],
})

const aggregation: AggregationSummary = {
  dimension: 'group',
  legibility_budget: 2,
  nodes: [
    { id: 'agg:group=core:application-component', dimension: 'group', dimension_value: 'core', entity_type: 'application-component', member_count: 2, member_ids: ['E1', 'E2'] },
    { id: 'agg:group=edge:application-component', dimension: 'group', dimension_value: 'edge', entity_type: 'application-component', member_count: 2, member_ids: ['E3', 'E9'] },
  ],
  edges: [
    { id: 'aggedge:1', source_aggregate_id: 'agg:group=core:application-component', target_aggregate_id: 'agg:group=edge:application-component', connection_type: 'archimate-serving', provenance: 'modeled', member_count: 3, member_connection_ids: ['C1', 'C2', 'C3'] },
  ],
}

describe('buildAggregateView', () => {
  it('renders collapsed aggregates as super-nodes with server bundle counts', () => {
    const view = buildAggregateView(aggregation, new Set(), [entity('E1')], [])
    expect(view.nodes.map((n) => n.id)).toEqual([
      'agg:group=core:application-component', 'agg:group=edge:application-component',
    ])
    expect(view.nodes[0].label).toBe('core · application-component (2)')
    expect(view.edges).toEqual([
      expect.objectContaining({ connType: 'archimate-serving', bundledCount: 3, provenance: 'modeled' }),
    ])
  })

  it('expanding one aggregate swaps in its returned members and re-bundles mixed edges', () => {
    const entities = [entity('E1'), entity('E2'), entity('E3')]
    const connections = [
      connection('C1', 'E1', 'E3'),
      connection('C2', 'E2', 'E3'),
      connection('C3', 'E1', 'E2'),
    ]
    const view = buildAggregateView(
      aggregation, new Set(['agg:group=core:application-component']), entities, connections,
    )
    const ids = view.nodes.map((n) => n.id)
    expect(ids).toContain('E1')
    expect(ids).toContain('E2')
    expect(ids).toContain('agg:group=edge:application-component')
    // E1→(edge agg) and E2→(edge agg) are separate bundles; E1→E2 renders individually.
    expect(view.edges).toHaveLength(3)
    const toAggregate = view.edges.filter((e) => isAggregateNodeId(e.target))
    expect(toAggregate).toHaveLength(2)
  })

  it('counts expanded members missing from the returned page honestly', () => {
    const view = buildAggregateView(
      aggregation, new Set(['agg:group=edge:application-component']), [entity('E3')], [],
    )
    expect(view.missingMemberCount).toBe(1)
    expect(view.nodes.map((n) => n.id)).toContain('E3')
  })
})

describe('aggregationIneffective', () => {
  it('flags single-aggregate and over-budget-aggregate outcomes', () => {
    expect(aggregationIneffective(aggregation)).toBe(false)
    expect(aggregationIneffective({ ...aggregation, nodes: aggregation.nodes.slice(0, 1) })).toBe(true)
    expect(aggregationIneffective({ ...aggregation, legibility_budget: 1 })).toBe(true)
  })
})
