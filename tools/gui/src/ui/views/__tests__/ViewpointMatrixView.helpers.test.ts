import { describe, expect, it } from 'vitest'
import {
  buildMatrixCells, cellEmphasisToken, cellKey, projectionByItemId, resolveMatrixAxes,
} from '../ViewpointMatrixView.helpers'
import { mkPresentation } from '../../../domain/viewpointPresentation'
import { mkGroup } from '../../../domain/viewpointCriteria'
import type { PresentationNode } from '../../../domain/viewpointPresentation'
import type { ConnectionItemSummary, ProjectedOccurrence, ViewpointExecutionResult, ViewpointProjection } from '../../../domain'

const conn = (overrides: Partial<ConnectionItemSummary> = {}): ConnectionItemSummary => ({
  id: 'c1', type: 'serving', source: 'a', target: 'b',
  certainty: null, hops: null, via_connection_ids: [], witness_steps: [], ...overrides,
})

const baseResult = (overrides: Partial<ViewpointExecutionResult> = {}): ViewpointExecutionResult => ({
  slug: 'vp', version: 1, query_schema: 1, repo_scope: 'both', executed_at: '2026-01-01T00:00:00Z',
  index_generation: 1, entity_ids: ['a', 'b', 'c'], connection_ids: [], entities: [], connections: [],
  total_entity_count: 3, returned_entity_count: 3, total_connection_count: 0, returned_connection_count: 0,
  truncated: false, entity_limit: 500, matrix_axes: null, warnings: [], duration_ms: 1, query_summary: '',
  anchor_ids: [], target_population: null, aggregation: null, bound_parameters: {}, trace_table: null,
  ...overrides,
})

describe('resolveMatrixAxes', () => {
  it('is empty when there is no result', () => {
    expect(resolveMatrixAxes(null, null)).toEqual({ rowIds: [], columnIds: [] })
  })

  it('uses the full population on both axes in grouped mode (or no presentation)', () => {
    expect(resolveMatrixAxes(null, baseResult())).toEqual({ rowIds: ['a', 'b', 'c'], columnIds: ['a', 'b', 'c'] })
    const grouped: PresentationNode = { ...mkPresentation('matrix'), rowBy: 'type', columnBy: 'group' }
    expect(resolveMatrixAxes(grouped, baseResult())).toEqual({ rowIds: ['a', 'b', 'c'], columnIds: ['a', 'b', 'c'] })
  })

  it('uses the disjoint matrix_axes populations in criteria mode', () => {
    const criteria: PresentationNode = {
      ...mkPresentation('matrix'), rowCriteria: mkGroup('entity'), columnCriteria: mkGroup('entity'),
    }
    const result = baseResult({ matrix_axes: { row_entity_ids: ['a'], column_entity_ids: ['b', 'c'] } })
    expect(resolveMatrixAxes(criteria, result)).toEqual({ rowIds: ['a'], columnIds: ['b', 'c'] })
  })
})

describe('buildMatrixCells', () => {
  it('populates a cell per connection, aggregating count and type slugs', () => {
    const cells = buildMatrixCells(['a'], ['b'], [conn(), conn({ id: 'c2', type: 'access' })])
    expect(cells.get(cellKey('a', 'b'))).toEqual({ connectionCount: 2, connectionTypes: ['access', 'serving'] })
  })

  it('respects the bridging invariant: either orientation counts, in the correct cell', () => {
    // source in column set, target in row set — reverse orientation
    const cells = buildMatrixCells(['b'], ['a'], [conn({ source: 'a', target: 'b' })])
    expect(cells.get(cellKey('b', 'a'))).toEqual({ connectionCount: 1, connectionTypes: ['serving'] })
  })

  it('does not double-count a self-loop connection', () => {
    const cells = buildMatrixCells(['a'], ['a'], [conn({ source: 'a', target: 'a' })])
    expect(cells.get(cellKey('a', 'a'))).toEqual({ connectionCount: 1, connectionTypes: ['serving'] })
  })

  it('excludes connections whose endpoints are not in the row/column sets', () => {
    const cells = buildMatrixCells(['a'], ['b'], [conn({ source: 'x', target: 'y' })])
    expect(cells.size).toBe(0)
  })

  it('populates both directions in a symmetric (same-population) matrix', () => {
    const cells = buildMatrixCells(['a', 'b'], ['a', 'b'], [conn({ source: 'a', target: 'b' })])
    expect(cells.get(cellKey('a', 'b'))?.connectionCount).toBe(1)
    expect(cells.get(cellKey('b', 'a'))?.connectionCount).toBe(1)
  })
})

const occurrence = (itemId: string, style: Record<string, string>): ProjectedOccurrence => ({
  item_id: itemId, item_kind: 'entity', state: 'visible', membership: 'primary', reasons: [], style,
})

describe('cellEmphasisToken', () => {
  it('prefers the row entity token, falling back to the column entity token', () => {
    const byId = new Map([
      ['row1', occurrence('row1', { cell_emphasis: 'critical' })],
      ['col1', occurrence('col1', { cell_emphasis: 'positive' })],
    ])
    expect(cellEmphasisToken('row1', 'col1', byId)).toBe('critical')
    expect(cellEmphasisToken('row-none', 'col1', byId)).toBe('positive')
    expect(cellEmphasisToken('row-none', 'col-none', byId)).toBeUndefined()
  })
})

describe('projectionByItemId', () => {
  it('indexes by item id, empty for a null projection', () => {
    expect(projectionByItemId(null).size).toBe(0)
    const projection: ViewpointProjection = { applied: true, target: 'repository', items: [occurrence('a', {})], stale_pin: false, warnings: [] }
    expect(projectionByItemId(projection).has('a')).toBe(true)
  })
})
