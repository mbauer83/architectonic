import { describe, expect, it } from 'vitest'
import {
  atDepthCap,
  attributeOptionLabel,
  attributeOptions,
  comparatorsFor,
  depthLabel,
  enumChoicesFor,
  isEntityReferencePath,
  valueKindOptions,
  conditionCoherenceIssue,
} from '../CriteriaTreeBuilder.helpers'
import type { CriteriaCatalog } from '../../../domain'
import { literalValue } from '../../../domain/viewpointCriteria'
import type { Comparator, ConditionNode } from '../../../domain/viewpointCriteria'

const CATALOG: CriteriaCatalog = {
  entity_types: ['application-component', 'process'],
  connection_types: ['archimate-serving'],
  specialization_slugs: ['business-process'],
  entity_attribute_types: { risk_score: 'number', lifecycle_stage: 'string' },
  connection_attribute_types: { strength: 'integer' },
  entity_attribute_enums: {
    lifecycle_stage: ['alpha', 'beta', 'ga'],
    domain: ['application', 'common'],
    status: ['draft', 'active', 'deprecated'],
    group: ['assurance', 'platform-core', 'uncategorized'],
  },
  connection_attribute_enums: {},
  symmetric_connection_types: [],
  reserved_entity_paths: ['id', 'name', 'type', 'specialization', 'group', 'domain', 'subdomain', 'status', 'version'],
  reserved_connection_paths: ['id', 'type', 'specialization'],
  depth_cap: 4,
  entity_type_domains: { 'application-component': 'application', process: 'common' },
  bindings: { select: ['entities', 'connections'], aggregate: ['count', 'sum', 'avg', 'min', 'max'], result_types: [] },
  parameters: { types: ['string', 'integer', 'number', 'date', 'boolean', 'slug', 'entity-id'] },
  derived: { traversal: ['direct', 'derived'], certainty: ['certain', 'potential'], reduce: ['count', 'sum', 'avg', 'min', 'max'] },
  connection_derivation: {},
}

describe('attributeOptions', () => {
  it('lists reserved entity paths before schema attributes, schema attributes sorted', () => {
    const options = attributeOptions('entity', CATALOG)
    expect(options.slice(0, 9).map((o) => o.path)).toEqual([
      'id', 'name', 'type', 'specialization', 'group', 'domain', 'subdomain', 'status', 'version',
    ])
    expect(options.slice(9).map((o) => o.path)).toEqual(['lifecycle_stage', 'risk_score'])
    expect(options.find((o) => o.path === 'risk_score')?.declaredType).toBe('number')
    expect(options.find((o) => o.path === 'type')?.reserved).toBe(true)
  })

  it('uses connection reserved paths and schema attributes for connection groups', () => {
    const options = attributeOptions('connection', CATALOG)
    expect(options.map((o) => o.path)).toEqual(['id', 'type', 'specialization', 'strength'])
  })
})

describe('comparatorsFor', () => {
  it('excludes numeric comparators for reserved paths', () => {
    const comparators = comparatorsFor({ path: 'status', reserved: true, declaredType: null })
    expect(comparators).not.toContain('gte')
    expect(comparators).toContain('eq')
  })

  it('includes numeric comparators for a numeric schema attribute', () => {
    const comparators = comparatorsFor({ path: 'risk_score', reserved: false, declaredType: 'number' })
    expect(comparators).toContain('gte')
  })

  it('excludes numeric comparators for a string schema attribute', () => {
    const comparators = comparatorsFor({ path: 'lifecycle_stage', reserved: false, declaredType: 'string' })
    expect(comparators).not.toContain('lt')
  })
})

describe('attributeOptionLabel', () => {
  it('labels the group facet as project membership', () => {
    expect(attributeOptionLabel({ path: 'group', reserved: true, declaredType: null })).toBe('group (project)')
  })

  it('passes every other path through unchanged', () => {
    expect(attributeOptionLabel({ path: 'status', reserved: true, declaredType: null })).toBe('status')
    expect(attributeOptionLabel({ path: 'risk_score', reserved: false, declaredType: 'number' })).toBe('risk_score')
  })
})

describe('enumChoicesFor', () => {
  it('serves the group facet from the catalog enum feed so project membership is a picker', () => {
    expect(enumChoicesFor('group', 'entity', CATALOG)).toEqual(['assurance', 'platform-core', 'uncategorized'])
  })

  it('offers known entity types for the type attribute on an entity group', () => {
    expect(enumChoicesFor('type', 'entity', CATALOG)).toEqual(['application-component', 'process'])
  })

  it('offers known connection types for the type attribute on a connection group', () => {
    expect(enumChoicesFor('type', 'connection', CATALOG)).toEqual(['archimate-serving'])
  })

  it('offers known specialization slugs regardless of group kind', () => {
    expect(enumChoicesFor('specialization', 'entity', CATALOG)).toEqual(['business-process'])
  })

  it('offers a schema attribute\'s declared enum values', () => {
    expect(enumChoicesFor('lifecycle_stage', 'entity', CATALOG)).toEqual(['alpha', 'beta', 'ga'])
  })

  it('offers the reserved domain/status facets from the entity enum map', () => {
    expect(enumChoicesFor('domain', 'entity', CATALOG)).toEqual(['application', 'common'])
    expect(enumChoicesFor('status', 'entity', CATALOG)).toEqual(['draft', 'active', 'deprecated'])
  })

  it('returns null (free-text) for attributes with no enumerable value set', () => {
    expect(enumChoicesFor('risk_score', 'entity', CATALOG)).toBeNull()
    expect(enumChoicesFor('name', 'entity', CATALOG)).toBeNull()
    expect(enumChoicesFor('strength', 'connection', CATALOG)).toBeNull()
  })
})

describe('isEntityReferencePath', () => {
  it('treats the reserved id path as an entity reference', () => {
    expect(isEntityReferencePath('id')).toBe(true)
  })

  it('treats non-id paths as non-references', () => {
    expect(isEntityReferencePath('name')).toBe(false)
    expect(isEntityReferencePath('type')).toBe(false)
    expect(isEntityReferencePath('risk_score')).toBe(false)
  })
})

describe('valueKindOptions', () => {
  it('offers literal and self for entity conditions, not source/target', () => {
    const kinds = valueKindOptions('entity').map((o) => o.kind)
    expect(kinds).toEqual(['literal', 'self'])
  })

  it('offers source and target for connection conditions', () => {
    const kinds = valueKindOptions('connection').map((o) => o.kind)
    expect(kinds).toEqual(['literal', 'self', 'source', 'target'])
  })
})

describe('depth meter', () => {
  it('labels nesting as 1-indexed out of the cap', () => {
    expect(depthLabel(0)).toBe('nesting 1 of 4')
    expect(depthLabel(3)).toBe('nesting 4 of 4')
  })

  it('flags the depth cap once nesting would reach it', () => {
    expect(atDepthCap(2)).toBe(false)
    expect(atDepthCap(3)).toBe(true)
  })
})

describe('conditionCoherenceIssue', () => {
  const condition = (comparator: Comparator, literal: unknown): ConditionNode => ({
    kind: 'condition', id: 'c1', attribute: 'status', comparator, value: literalValue(literal), negate: false,
  })

  it('flags exists/absent carrying a value, accepts the unset and empty literal', () => {
    expect(conditionCoherenceIssue(condition('exists', 'x'))).toBe("'exists' takes no value")
    expect(conditionCoherenceIssue(condition('absent', 'x'))).toBe("'absent' takes no value")
    expect(conditionCoherenceIssue(condition('exists', null))).toBeNull()
    expect(conditionCoherenceIssue(condition('exists', ''))).toBeNull()
  })

  it('flags an empty membership list and a non-numeric ordering value', () => {
    expect(conditionCoherenceIssue(condition('in', []))).toBe("'in' needs at least one value")
    expect(conditionCoherenceIssue(condition('in', ['a']))).toBeNull()
    expect(conditionCoherenceIssue(condition('gte', 'not-a-number'))).toBe("'gte' needs a number or date")
    expect(conditionCoherenceIssue(condition('gte', '4'))).toBeNull()
    expect(conditionCoherenceIssue(condition('lt', '2026-01-01'))).toBeNull()
  })

  it('stays quiet for coherent equality conditions and non-literal values', () => {
    expect(conditionCoherenceIssue(condition('eq', 'active'))).toBeNull()
  })
})
