import { describe, expect, it } from 'vitest'
import { bindingValue, endpointValue, literalValue, mkGroup, mkQuery, parameterValue, selfValue } from './viewpointCriteria'
import {
  connectionSelectionFromMapping,
  connectionSelectionToMapping,
  groupFromMapping,
  groupToMapping,
  neighborInclusionFromMapping,
  neighborInclusionToMapping,
  queryFromMapping,
  queryToMapping,
} from './viewpointCriteriaSerialization'
import { mkDerivedAttribute, mkQueryBinding, mkQueryParameter } from './viewpointBindings'

describe('condition value refs', () => {
  it('serializes a literal value as a plain scalar', () => {
    const group = mkGroup('entity')
    group.children = [{ kind: 'condition', id: 'c1', attribute: 'status', comparator: 'eq', value: literalValue('active'), negate: false }]
    expect(groupToMapping(group).children).toEqual([{ kind: 'condition', attribute: 'status', comparator: 'eq', value: 'active' }])
  })

  it('serializes a self attribute reference as {from: self, attribute}', () => {
    const group = mkGroup('entity')
    group.children = [{ kind: 'condition', id: 'c1', attribute: 'end_date', comparator: 'gte', value: selfValue('start_date'), negate: false }]
    expect(groupToMapping(group).children).toEqual([
      { kind: 'condition', attribute: 'end_date', comparator: 'gte', value: { from: 'self', attribute: 'start_date' } },
    ])
  })

  it('serializes an endpoint attribute reference as {from: source|target, attribute}', () => {
    const group = mkGroup('connection')
    group.children = [{ kind: 'condition', id: 'c1', attribute: 'strength', comparator: 'gte', value: endpointValue('target', 'threshold'), negate: false }]
    expect(groupToMapping(group).children).toEqual([
      { kind: 'condition', attribute: 'strength', comparator: 'gte', value: { from: 'target', attribute: 'threshold' } },
    ])
  })

  it('round-trips a self reference through from-mapping', () => {
    const parsed = groupFromMapping(
      { kind: 'group', conjunction: 'and', children: [{ kind: 'condition', attribute: 'end_date', comparator: 'gte', value: { from: 'self', attribute: 'start_date' } }] },
      'entity',
    )
    const condition = parsed.children[0]
    expect(condition.kind).toBe('condition')
    expect(condition.kind === 'condition' && condition.value).toEqual(selfValue('start_date'))
  })

  it('serializes a parameter reference as {from: parameter, name}', () => {
    const group = mkGroup('entity')
    group.children = [{ kind: 'condition', id: 'c1', attribute: 'status', comparator: 'eq', value: parameterValue('anchor'), negate: false }]
    expect(groupToMapping(group).children).toEqual([
      { kind: 'condition', attribute: 'status', comparator: 'eq', value: { from: 'parameter', name: 'anchor' } },
    ])
  })

  it('serializes a binding reference with project/aggregate/quantifier, omitting unset ones', () => {
    const group = mkGroup('entity')
    group.children = [{
      kind: 'condition', id: 'c1', attribute: 'strength', comparator: 'gte',
      value: bindingValue('critical-processes', { project: 'threshold', aggregate: 'max' }), negate: false,
    }]
    expect(groupToMapping(group).children).toEqual([{
      kind: 'condition', attribute: 'strength', comparator: 'gte',
      value: { from: 'binding', name: 'critical-processes', project: 'threshold', aggregate: 'max' },
    }])
  })

  it('round-trips a binding reference with a quantifier through from-mapping', () => {
    const raw = { from: 'binding', name: 'critical-processes', project: 'id', quantifier: 'any' }
    const parsed = groupFromMapping({ kind: 'group', conjunction: 'and', children: [{ kind: 'condition', attribute: 'id', comparator: 'in', value: raw }] }, 'entity')
    const condition = parsed.children[0]
    expect(condition.kind === 'condition' && condition.value).toEqual(bindingValue('critical-processes', { project: 'id', quantifier: 'any' }))
    expect(groupToMapping(parsed).children).toEqual([{ kind: 'condition', attribute: 'id', comparator: 'in', value: raw }])
  })

  it('omits negate when false and includes it when true', () => {
    const group = mkGroup('entity')
    group.children = [
      { kind: 'condition', id: 'c1', attribute: 'type', comparator: 'eq', value: literalValue('x'), negate: false },
      { kind: 'condition', id: 'c2', attribute: 'type', comparator: 'eq', value: literalValue('y'), negate: true },
    ]
    const mapped = groupToMapping(group).children as Record<string, unknown>[]
    expect(mapped[0]).not.toHaveProperty('negate')
    expect(mapped[1].negate).toBe(true)
  })
})

describe('incident conditions', () => {
  it('omits direction when either, includes it otherwise; traversal is always explicit', () => {
    const outgoing = groupFromMapping(
      { kind: 'group', conjunction: 'and', children: [{ kind: 'incident', direction: 'outgoing' }] },
      'entity',
    )
    expect(groupToMapping(outgoing).children).toEqual([
      { kind: 'incident', direction: 'outgoing', traversal: 'direct' },
    ])

    const either = groupFromMapping({ kind: 'group', conjunction: 'and', children: [{ kind: 'incident' }] }, 'entity')
    expect(groupToMapping(either).children).toEqual([{ kind: 'incident', traversal: 'direct' }])
  })

  it('nests connection_criteria and endpoint_criteria', () => {
    const raw = {
      kind: 'group', conjunction: 'and',
      children: [{
        kind: 'incident',
        connection_criteria: { kind: 'group', conjunction: 'and', children: [{ kind: 'condition', attribute: 'type', comparator: 'eq', value: 'archimate-serving' }] },
        endpoint_criteria: { kind: 'group', conjunction: 'and', children: [{ kind: 'condition', attribute: 'type', comparator: 'eq', value: 'process' }] },
      }],
    }
    const parsed = groupFromMapping(raw, 'entity')
    expect(groupToMapping(parsed)).toEqual({
      ...raw,
      children: [{ ...raw.children[0], traversal: 'direct' }],
    })
  })

  it('round-trips a non-default traversal instead of silently dropping it', () => {
    for (const traversal of ['derived', 'both'] as const) {
      const parsed = groupFromMapping(
        { kind: 'group', conjunction: 'and', children: [{ kind: 'incident', traversal }] },
        'entity',
      )
      expect(groupToMapping(parsed).children).toEqual([{ kind: 'incident', traversal }])
    }
  })
})

describe('neighbor inclusion', () => {
  it('round-trips direction and both criteria legs', () => {
    const raw = {
      direction: 'outgoing',
      connection_criteria: { kind: 'group', conjunction: 'and', children: [{ kind: 'condition', attribute: 'type', comparator: 'eq', value: 'archimate-serving' }] },
      neighbor_criteria: { kind: 'group', conjunction: 'and', children: [{ kind: 'condition', attribute: 'type', comparator: 'eq', value: 'process' }] },
    }
    const parsed = neighborInclusionFromMapping(raw)
    expect(neighborInclusionToMapping(parsed)).toEqual(raw)
  })

  it('defaults traversal to direct and omits it, include_potential, and max_hops when unset', () => {
    const parsed = neighborInclusionFromMapping({})
    expect(parsed.traversal).toBe('direct')
    expect(parsed.includePotential).toBe(false)
    expect(parsed.maxHops).toBeNull()
    expect(neighborInclusionToMapping(parsed)).toEqual({})
  })

  it('round-trips a derived traversal with include_potential and max_hops', () => {
    const raw = { traversal: 'derived', include_potential: true, max_hops: 4 }
    const parsed = neighborInclusionFromMapping(raw)
    expect(parsed).toMatchObject({ traversal: 'derived', includePotential: true, maxHops: 4 })
    expect(neighborInclusionToMapping(parsed)).toEqual(raw)
  })
})

describe('connection selection', () => {
  it('omits enabled when true and the default empty criteria', () => {
    const selection = connectionSelectionFromMapping(null)
    expect(connectionSelectionToMapping(selection)).toEqual({})
  })

  it('serializes enabled:false and non-default criteria', () => {
    const raw = {
      enabled: false,
      criteria: { kind: 'group', conjunction: 'and', children: [{ kind: 'condition', attribute: 'type', comparator: 'eq', value: 'archimate-serving' }] },
    }
    const parsed = connectionSelectionFromMapping(raw)
    expect(connectionSelectionToMapping(parsed)).toEqual(raw)
  })

  it('round-trips a both-traversal connection selection', () => {
    const raw = { traversal: 'both', include_potential: true, max_hops: 2 }
    const parsed = connectionSelectionFromMapping(raw)
    expect(parsed).toMatchObject({ traversal: 'both', includePotential: true, maxHops: 2 })
    expect(connectionSelectionToMapping(parsed)).toEqual(raw)
  })
})

describe('query bindings/parameters/derived', () => {
  it('omits bindings/parameters/derived entirely when the query declares none', () => {
    expect(queryToMapping(mkQuery())).not.toHaveProperty('bindings')
    expect(queryToMapping(mkQuery())).not.toHaveProperty('parameters')
    expect(queryToMapping(mkQuery())).not.toHaveProperty('derived')
  })

  it('round-trips a security-signal derived attribute without inventing graph keys', () => {
    const query = mkQuery()
    const attribute = mkDerivedAttribute()
    attribute.name = 'open_vulns'
    attribute.source = 'security-signal'
    attribute.metric = 'distinct_open_vulnerabilities'
    query.derived = [attribute]
    const mapped = queryToMapping(query)
    expect(mapped.derived).toEqual([{
      name: 'open_vulns', source: 'security-signal', metric: 'distinct_open_vulnerabilities',
    }])
    const parsed = queryFromMapping(mapped)
    expect(parsed.derived[0]).toMatchObject({
      name: 'open_vulns', source: 'security-signal', metric: 'distinct_open_vulnerabilities',
    })
    // A graph attribute stays exactly as before — no source key on the wire.
    const graph = mkDerivedAttribute()
    graph.name = 'dependents'
    query.derived = [graph]
    expect((queryToMapping(query).derived as Record<string, unknown>[])[0]).not.toHaveProperty('source')
  })

  it('round-trips a set-cardinality entity binding through query mapping', () => {
    const query = mkQuery()
    const binding = mkQueryBinding()
    binding.name = 'critical-processes'
    binding.criteria.children = [{ kind: 'condition', id: 'c1', attribute: 'type', comparator: 'eq', value: literalValue('process'), negate: false }]
    query.bindings = [binding]
    const mapped = queryToMapping(query)
    expect(mapped.bindings).toEqual([{
      name: 'critical-processes', result_type: 'entities[process]', select: 'entities',
      criteria: { kind: 'group', conjunction: 'and', children: [{ kind: 'condition', attribute: 'type', comparator: 'eq', value: 'process' }] },
    }])
    const parsed = queryFromMapping(mapped)
    expect(parsed.bindings[0].name).toBe('critical-processes')
    expect(parsed.bindings[0].select).toBe('entities')
    expect(parsed.bindings[0].cardinality).toBe('set')
  })

  it('round-trips a tuple binding referencing earlier bindings by name', () => {
    const query = mkQuery()
    const first = mkQueryBinding()
    first.name = 'a'
    const second = mkQueryBinding()
    second.name = 'b'
    const tupleBinding = mkQueryBinding()
    tupleBinding.name = 'pair'
    tupleBinding.mode = 'tuple'
    tupleBinding.tupleOf = ['a', 'b']
    query.bindings = [first, second, tupleBinding]
    const mapped = queryToMapping(query)
    const pairMapping = (mapped.bindings as Record<string, unknown>[])[2]
    expect(pairMapping.tuple).toEqual(['a', 'b'])
    expect(pairMapping.result_type).toBe('tuple[entities[], entities[]]')
    const parsed = queryFromMapping(mapped)
    expect(parsed.bindings[2].mode).toBe('tuple')
    expect(parsed.bindings[2].tupleOf).toEqual(['a', 'b'])
  })

  it('round-trips a parameter, omitting required:true and an empty default/description', () => {
    const query = mkQuery()
    const parameter = mkQueryParameter()
    parameter.name = 'anchor'
    parameter.valueType = 'entity-id'
    query.parameters = [parameter]
    const mapped = queryToMapping(query)
    expect(mapped.parameters).toEqual([{ name: 'anchor', type: 'entity-id' }])
    const parsed = queryFromMapping(mapped)
    expect(parsed.parameters[0]).toMatchObject({ name: 'anchor', valueType: 'entity-id', required: true })
  })

  it('round-trips a derived attribute with a connection.<attr> source', () => {
    const query = mkQuery()
    const attribute = {
      id: 'd1', name: 'impact-distance', source: 'graph' as const, metric: null,
      direction: 'either' as const, traversal: 'derived' as const,
      includePotential: false, maxHops: 3, connectionCriteria: null, endpointCriteria: null,
      reduce: 'min' as const, ofHead: 'relationship-hops' as const, ofAttribute: null,
    }
    query.derived = [attribute]
    const mapped = queryToMapping(query)
    expect(mapped.derived).toEqual([{ name: 'impact-distance', traversal: 'derived', max_hops: 3, reduce: 'min', of: 'relationship.hops' }])
    const parsed = queryFromMapping(mapped)
    expect(parsed.derived[0]).toMatchObject({ name: 'impact-distance', traversal: 'derived', maxHops: 3, reduce: 'min', ofHead: 'relationship-hops' })
  })
})
