import { describe, expect, it } from 'vitest'
import { buildLayeredViewQuery } from './layeredViewQuery'
import { mkCondition, mkGroup, literalValue } from './viewpointCriteria'
import { queryToMapping } from './viewpointCriteriaSerialization'

describe('buildLayeredViewQuery', () => {
  it('builds an id-in-list root selection with a derived neighbor inclusion and both-traversal connections', () => {
    const neighborCriteria = mkGroup('entity')
    neighborCriteria.children = [{ ...mkCondition('domain', 'eq'), value: literalValue('technology') }]
    const query = buildLayeredViewQuery({
      rootEntityIds: ['ENT@a', 'ENT@b'],
      rootCriteria: null,
      neighborCriteria,
      includePotential: false,
      maxHops: 3,
    })
    const mapped = queryToMapping(query)
    expect(mapped.entity_criteria).toEqual({
      kind: 'group', conjunction: 'and',
      children: [{ kind: 'condition', attribute: 'id', comparator: 'in', value: ['ENT@a', 'ENT@b'] }],
    })
    expect(mapped.include_connected).toEqual([{
      neighbor_criteria: { kind: 'group', conjunction: 'and', children: [{ kind: 'condition', attribute: 'domain', comparator: 'eq', value: 'technology' }] },
      traversal: 'derived', max_hops: 3,
    }])
    expect(mapped.connections).toEqual({ traversal: 'both', max_hops: 3 })
  })

  it('prefers rootCriteria over rootEntityIds when both are given', () => {
    const rootCriteria = mkGroup('entity')
    rootCriteria.children = [{ ...mkCondition('type', 'eq'), value: literalValue('business-process') }]
    const query = buildLayeredViewQuery({
      rootEntityIds: ['ENT@ignored'],
      rootCriteria,
      neighborCriteria: mkGroup('entity'),
      includePotential: true,
      maxHops: 2,
    })
    const mapped = queryToMapping(query)
    expect(mapped.entity_criteria).toEqual({
      kind: 'group', conjunction: 'and', children: [{ kind: 'condition', attribute: 'type', comparator: 'eq', value: 'business-process' }],
    })
    expect(mapped.connections).toEqual({ traversal: 'both', include_potential: true, max_hops: 2 })
  })
})
