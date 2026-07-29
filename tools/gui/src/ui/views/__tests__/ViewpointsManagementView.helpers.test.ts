import { describe, expect, it } from 'vitest'
import {
  csvToList, executionRouteFor, firstErrorNodeId, formatPreviewCounts, formatScopeSummary, isSemanticEdit, listToCsv,
  suggestForkSlug,
} from '../ViewpointsManagementView.helpers'
import { mkDefinitionDraft, mkScope } from '../../../domain/viewpointDefinitionDraft'
import { mkPresentation } from '../../../domain/viewpointPresentation'
import { presentationToMapping } from '../../../domain/viewpointPresentationSerialization'
import type { ViewpointDefinitionEnvelope, ViewpointValidationIssue } from '../../../domain'

const mkEnvelope = (representation: Parameters<typeof mkPresentation>[0] | null): ViewpointDefinitionEnvelope => ({
  slug: 'goal-realization', version: 1, name: 'Goal Realization', tier: 'module',
  scope_summary: { unrestricted: true }, query_summary: null, fork_status: null,
  presentation: representation === null ? undefined : presentationToMapping(mkPresentation(representation)),
})

describe('executionRouteFor', () => {
  it('routes exploration-representation definitions to /graph', () => {
    expect(executionRouteFor(mkEnvelope('exploration'))).toEqual({
      path: '/graph', query: { viewpoint: 'goal-realization' },
    })
  })

  it('routes table/matrix/diagram representations to their dedicated surfaces', () => {
    expect(executionRouteFor(mkEnvelope('table')).path).toBe('/entities')
    expect(executionRouteFor(mkEnvelope('matrix')).path).toBe('/viewpoints/matrix')
    expect(executionRouteFor(mkEnvelope('diagram')).path).toBe('/viewpoints/diagram')
  })

  it('falls back to exploration when the definition carries no presentation', () => {
    expect(executionRouteFor(mkEnvelope(null)).path).toBe('/graph')
  })
})

describe('suggestForkSlug', () => {
  it('appends -copy when free', () => {
    expect(suggestForkSlug('capability-map', ['capability-map'])).toBe('capability-map-copy')
  })

  it('counts up past every taken suggestion across all tiers', () => {
    const taken = ['capability-map', 'capability-map-copy', 'capability-map-copy-2']
    expect(suggestForkSlug('capability-map', taken)).toBe('capability-map-copy-3')
  })
})

describe('isSemanticEdit', () => {
  it('is false when only descriptive fields change', () => {
    const original = mkDefinitionDraft()
    original.slug = 'x'
    original.name = 'X'
    const current = { ...original, description: 'now described', rationale: 'because' }
    expect(isSemanticEdit(current, original)).toBe(false)
  })

  it('is true when scope changes', () => {
    const original = mkDefinitionDraft()
    original.slug = 'x'
    const current = { ...original, scope: { ...mkScope(), entityTypes: ['application-component'] } }
    expect(isSemanticEdit(current, original)).toBe(true)
  })

  it('is true when an exclusion field changes', () => {
    const original = mkDefinitionDraft()
    original.slug = 'x'
    const current = { ...original, scope: { ...mkScope(), excludedDomains: ['application'] } }
    expect(isSemanticEdit(current, original)).toBe(true)
  })

  it('is true when the query criteria changes', () => {
    const original = mkDefinitionDraft()
    original.slug = 'x'
    const current = structuredClone(original)
    current.query!.entityCriteria.children.push({
      kind: 'condition', id: 'n999', attribute: 'status', comparator: 'eq', value: { kind: 'literal', literal: 'active' }, negate: false,
    })
    expect(isSemanticEdit(current, original)).toBe(true)
  })
})

describe('csv helpers', () => {
  it('round-trips a comma-separated list, trimming whitespace', () => {
    expect(csvToList('a, b ,  c')).toEqual(['a', 'b', 'c'])
    expect(listToCsv(['a', 'b', 'c'])).toBe('a, b, c')
  })

  it('drops empty entries', () => {
    expect(csvToList('a, , b,')).toEqual(['a', 'b'])
  })
})

describe('formatScopeSummary', () => {
  it('reports unrestricted', () => {
    expect(formatScopeSummary({ unrestricted: true })).toBe('unrestricted')
  })

  it('lists entity and connection types when restricted', () => {
    expect(formatScopeSummary({ unrestricted: false, entity_types: ['application-component'] }))
      .toBe('entities: application-component')
    expect(formatScopeSummary({ unrestricted: false, entity_types: ['a'], connection_types: ['b'] }))
      .toBe('entities: a; connections: b')
  })

  it('describes exclusion fields', () => {
    expect(formatScopeSummary({ unrestricted: false, excluded_domains: ['application'] }))
      .toBe('excludes domains: application')
    expect(formatScopeSummary({
      unrestricted: false, excluded_entity_types: ['a'], excluded_connection_types: ['b'],
    })).toBe('excludes entities: a; excludes connections: b')
  })
})

describe('formatPreviewCounts', () => {
  it('is empty when there is no preview result yet', () => {
    expect(formatPreviewCounts(null)).toBe('')
  })

  it('pluralizes entity/connection nouns correctly', () => {
    expect(formatPreviewCounts({ total_entity_count: 1, total_connection_count: 1 })).toBe('1 entity / 1 connection')
    expect(formatPreviewCounts({ total_entity_count: 0, total_connection_count: 5 })).toBe('0 entities / 5 connections')
    expect(formatPreviewCounts({ total_entity_count: 3, total_connection_count: 2 })).toBe('3 entities / 2 connections')
  })
})

describe('firstErrorNodeId', () => {
  it('is null when there are no error-severity issues', () => {
    const draft = mkDefinitionDraft()
    const warningOnly: ViewpointValidationIssue[] = [
      { severity: 'warning', code: 'w', path: '/query/entity_criteria', message: 'm', expected: null, found: null },
    ]
    expect(firstErrorNodeId(warningOnly, draft)).toBeNull()
  })

  it('maps the first error issue to its builder node, ignoring a leading warning', () => {
    const draft = mkDefinitionDraft()
    const entityCriteriaId = draft.query!.entityCriteria.id
    const issues: ViewpointValidationIssue[] = [
      { severity: 'warning', code: 'w', path: '/slug', message: 'descriptive', expected: null, found: null },
      { severity: 'error', code: 'e', path: '/query/entity_criteria', message: 'bad criteria', expected: null, found: null },
    ]
    expect(firstErrorNodeId(issues, draft)).toBe(entityCriteriaId)
  })
})
