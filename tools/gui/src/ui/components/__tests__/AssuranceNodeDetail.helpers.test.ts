/**
 * Pure logic tests for AssuranceNodeDetail edge helpers: grouping by connection
 * type, name-first endpoint labels sourced from the server-enriched payload, and
 * the browse deep-link shape.
 */
import { describe, it, expect } from 'vitest'
import {
  endpointLabel,
  groupByType,
  nodeBrowsePath,
  type AssuranceEdge,
} from '../AssuranceNodeDetail.helpers'

function edge(overrides: Partial<AssuranceEdge> = {}): AssuranceEdge {
  return {
    edge_id: 'EDG@1',
    source_id: 'HAZ@1',
    target_id: 'LSS@1',
    conn_type: 'leads-to',
    source_name: 'Hazard One',
    source_type: 'hazard',
    target_name: 'Loss One',
    target_type: 'loss',
    ...overrides,
  }
}

describe('groupByType', () => {
  it('groups edges by connection type preserving order within groups', () => {
    const edges = [
      edge({ edge_id: 'E1', conn_type: 'leads-to' }),
      edge({ edge_id: 'E2', conn_type: 'derives' }),
      edge({ edge_id: 'E3', conn_type: 'leads-to' }),
    ]
    const groups = groupByType(edges)
    expect(Object.keys(groups)).toEqual(['leads-to', 'derives'])
    expect(groups['leads-to'].map(e => e.edge_id)).toEqual(['E1', 'E3'])
    expect(groups['derives'].map(e => e.edge_id)).toEqual(['E2'])
  })

  it('returns an empty record for no edges', () => {
    expect(groupByType([])).toEqual({})
  })
})

describe('endpointLabel', () => {
  it('prefers the server-enriched name over the raw id', () => {
    expect(endpointLabel(edge(), 'source')).toBe('Hazard One')
    expect(endpointLabel(edge(), 'target')).toBe('Loss One')
  })

  it('falls back to the id when no name is present', () => {
    const bare = edge({ source_name: undefined, target_name: undefined })
    expect(endpointLabel(bare, 'source')).toBe('HAZ@1')
    expect(endpointLabel(bare, 'target')).toBe('LSS@1')
  })
})

describe('nodeBrowsePath', () => {
  it('deep-links into the browse surface, which is /assurance itself', () => {
    expect(nodeBrowsePath('HAZ@1')).toEqual({
      path: '/assurance',
      query: { node_id: 'HAZ@1' },
    })
  })
})
