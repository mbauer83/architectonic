import { describe, expect, it } from 'vitest'
import {
  executionQuery, parametersFromQuery, verifiedReferenceMismatch, verifiedReferenceQuery,
} from './viewpointUrlState'
import type { ViewpointExecutionResult } from '../../domain'

const result = (generation: number | null): ViewpointExecutionResult => ({
  slug: 'vp', version: 1, query_schema: 1, repo_scope: 'both', executed_at: '2026-01-01T00:00:00Z',
  index_generation: generation, entity_ids: [], connection_ids: [], entities: [], connections: [],
  total_entity_count: 0, returned_entity_count: 0, total_connection_count: 0, returned_connection_count: 0,
  truncated: false, entity_limit: 500, matrix_axes: null, warnings: [], duration_ms: 1, query_summary: '',
  anchor_ids: [], target_population: null, aggregation: null, bound_parameters: {}, trace_table: null,
})

describe('executionQuery / parametersFromQuery', () => {
  it('round-trips slug and parameters through the URL', () => {
    const query = executionQuery('element-dependents', { anchor: 'DOB@1.xx.idx' })
    expect(query).toEqual({ viewpoint: 'element-dependents', 'param.anchor': 'DOB@1.xx.idx' })
    expect(parametersFromQuery(query as never)).toEqual({ anchor: 'DOB@1.xx.idx' })
  })

  it('carries nothing but the execution state — stale keys never leak in', () => {
    expect(Object.keys(executionQuery('vp', {}))).toEqual(['viewpoint'])
  })

  it('round-trips a SET parameter as repeated ordered keys, not a joined string', () => {
    const query = executionQuery('motivation-coverage', { scope: ['goal', 'requirement'] })
    expect(query['param.scope']).toEqual(['goal', 'requirement'])
    expect(parametersFromQuery(query as never)).toEqual({ scope: ['goal', 'requirement'] })
  })

  it('reads a repeated query key back as an array and a single one as a string', () => {
    expect(parametersFromQuery({ 'param.scope': ['goal', 'outcome'], 'param.gaps_only': 'true' })).toEqual({
      scope: ['goal', 'outcome'],
      gaps_only: 'true',
    })
  })
})

describe('verifiedReferenceQuery', () => {
  it('adds the pins on top of the live query', () => {
    const query = verifiedReferenceQuery(
      { viewpoint: 'vp' },
      { version: 3, definitionDigest: 'abc', generation: 71 },
    )
    expect(query).toEqual({ viewpoint: 'vp', vpv: '3', vpd: 'abc', gen: '71' })
  })
})

describe('verifiedReferenceMismatch', () => {
  it('is silent for live links', () => {
    expect(verifiedReferenceMismatch({ viewpoint: 'vp' }, result(71), 'abc')).toBeNull()
  })

  it('is silent when the pinned state still matches', () => {
    const query = { viewpoint: 'vp', vpd: 'abc', gen: '71' }
    expect(verifiedReferenceMismatch(query, result(71), 'abc')).toBeNull()
  })

  it('reports a moved model generation', () => {
    const query = { viewpoint: 'vp', vpd: 'abc', gen: '71' }
    const statement = verifiedReferenceMismatch(query, result(85), 'abc')
    expect(statement).toContain('re-executed at model generation 85')
    expect(statement).toContain('captured at 71')
    expect(statement).toContain('results may differ')
  })

  it('reports a changed definition', () => {
    const query = { viewpoint: 'vp', vpd: 'abc', gen: '71' }
    const statement = verifiedReferenceMismatch(query, result(71), 'DIFFERENT')
    expect(statement).toContain('definition has changed')
  })

  it('is silent before any execution', () => {
    expect(verifiedReferenceMismatch({ viewpoint: 'vp', gen: '71' }, null, 'abc')).toBeNull()
  })
})
