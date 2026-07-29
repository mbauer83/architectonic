import { describe, expect, it } from 'vitest'
import { capabilitiesFor, derivedLegend, numericAttributeOptions } from '../StyleRuleEditor.helpers'
import { mkGroup } from '../../../domain/viewpointCriteria'
import { mkPresentation } from '../../../domain/viewpointPresentation'
import type { CriteriaCatalog } from '../../../domain'

const CATALOG: CriteriaCatalog = {
  entity_types: [], connection_types: [], specialization_slugs: [],
  entity_attribute_types: { risk_score: 'number', lifecycle_stage: 'string', launched_on: 'date' },
  connection_attribute_types: {},
  entity_attribute_enums: {}, connection_attribute_enums: {},
  symmetric_connection_types: [], reserved_entity_paths: [], reserved_connection_paths: [], depth_cap: 4,
  entity_type_domains: {},
  bindings: { select: ['entities', 'connections'], aggregate: ['count', 'sum', 'avg', 'min', 'max'], result_types: [] },
  parameters: { types: ['string', 'integer', 'number', 'date', 'boolean', 'slug', 'entity-id'] },
  derived: { traversal: ['direct', 'derived'], certainty: ['certain', 'potential'], reduce: ['count', 'sum', 'avg', 'min', 'max'] },
  connection_derivation: {},
}

describe('capabilitiesFor', () => {
  it('lists exploration capabilities', () => {
    expect(capabilitiesFor('exploration')).toContain('node_color')
    expect(capabilitiesFor('matrix')).toEqual(['row_by', 'column_by', 'cell_emphasis'])
  })
})

describe('numericAttributeOptions', () => {
  it('keeps only number/date schema attributes', () => {
    expect(numericAttributeOptions(CATALOG)).toEqual(['launched_on', 'risk_score'])
  })
})

describe('derivedLegend', () => {
  it('is empty for a presentation with no styling', () => {
    expect(derivedLegend(mkPresentation('table'))).toEqual([])
  })

  it('counts match-mode rule values and range-band values, deduping tokens', () => {
    const presentation = mkPresentation('table')
    presentation.stylingRules = [
      {
        id: 'r1', capability: 'badges', appliesTo: [], mode: 'match', matchCriteria: mkGroup('entity'),
        rangeAttribute: null, rangeBands: [], value: 'critical',
        scaleAttribute: null, scaleMin: null, scaleMax: null, scaleTokens: null,
        sourceCriteria: null, targetCriteria: null, disabled: false,
      },
      {
        id: 'r2', capability: 'badges', appliesTo: [], mode: 'range', matchCriteria: null, rangeAttribute: 'risk_score',
        rangeBands: [
          { id: 'b1', minimum: null, maximum: 4, value: 'positive' },
          { id: 'b2', minimum: 4, maximum: null, value: 'critical' },
        ],
        value: null,
        scaleAttribute: null, scaleMin: null, scaleMax: null, scaleTokens: null,
        sourceCriteria: null, targetCriteria: null, disabled: false,
      },
    ]
    presentation.defaultStyle = { badges: 'neutral' }
    const legend = derivedLegend(presentation)
    expect(legend).toEqual([
      { token: 'critical', usageCount: 2 },
      { token: 'positive', usageCount: 1 },
      { token: 'neutral', usageCount: 1 },
    ])
  })

  it('counts scale-mode endpoint values, including explicit hex colors', () => {
    const presentation = mkPresentation('exploration')
    presentation.stylingRules = [
      {
        id: 'r1', capability: 'node_color', appliesTo: [], mode: 'scale', matchCriteria: null,
        rangeAttribute: null, rangeBands: [], value: null,
        scaleAttribute: 'derived.impact-distance', scaleMin: null, scaleMax: null,
        scaleTokens: ['heat-near', '#123456'],
        sourceCriteria: null, targetCriteria: null, disabled: false,
      },
    ]
    expect(derivedLegend(presentation)).toEqual([
      { token: 'heat-near', usageCount: 1 },
      { token: '#123456', usageCount: 1 },
    ])
  })
})
