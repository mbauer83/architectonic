import { describe, expect, it } from 'vitest'
import { literalValue, mkGroup } from './viewpointCriteria'
import {
  derivedOfFromString,
  derivedOfStringFor,
  inferTypeUnion,
  mkDerivedAttribute,
  mkQueryBinding,
  projectedScalarKind,
  resultTypeStringFor,
} from './viewpointBindings'

describe('inferTypeUnion', () => {
  it('is open (empty) for an unrestricted criteria tree', () => {
    expect(inferTypeUnion(mkGroup('entity'))).toEqual([])
  })

  it('collects positive eq/in type conditions on the top-level AND spine, sorted and deduped', () => {
    const group = mkGroup('entity', 'and')
    group.children = [
      { kind: 'condition', id: 'c1', attribute: 'type', comparator: 'eq', value: literalValue('process'), negate: false },
      { kind: 'condition', id: 'c2', attribute: 'type', comparator: 'in', value: literalValue(['goal', 'process']), negate: false },
    ]
    expect(inferTypeUnion(group)).toEqual(['goal', 'process'])
  })

  it('ignores a negated type condition (negation is not a positive narrowing)', () => {
    const group = mkGroup('entity', 'and')
    group.children = [
      { kind: 'condition', id: 'c1', attribute: 'type', comparator: 'eq', value: literalValue('process'), negate: true },
    ]
    expect(inferTypeUnion(group)).toEqual([])
  })

  it('is open for an OR-conjunction root, since OR cannot be conservatively narrowed', () => {
    const group = mkGroup('entity', 'or')
    group.children = [
      { kind: 'condition', id: 'c1', attribute: 'type', comparator: 'eq', value: literalValue('process'), negate: false },
    ]
    expect(inferTypeUnion(group)).toEqual([])
  })

  it('ignores a non-type attribute condition', () => {
    const group = mkGroup('entity', 'and')
    group.children = [
      { kind: 'condition', id: 'c1', attribute: 'status', comparator: 'eq', value: literalValue('active'), negate: false },
    ]
    expect(inferTypeUnion(group)).toEqual([])
  })
})

describe('projectedScalarKind', () => {
  it('uses the schema-declared type when known', () => {
    expect(projectedScalarKind('risk_score', 'entity', { entity: { risk_score: 'number' }, connection: {} })).toBe('number')
  })

  it('falls back to slug for the reserved id path, string otherwise', () => {
    expect(projectedScalarKind('id', 'entity', { entity: {}, connection: {} })).toBe('slug')
    expect(projectedScalarKind('status', 'entity', { entity: {}, connection: {} })).toBe('string')
  })
})

describe('resultTypeStringFor', () => {
  const attributeTypes = { entity: { risk_score: 'number' }, connection: {} }

  it('formats an instance-cardinality entity binding with an inferred type union', () => {
    const binding = mkQueryBinding()
    binding.name = 'anchor'
    binding.cardinality = 'instance'
    binding.criteria.children = [
      { kind: 'condition', id: 'c1', attribute: 'type', comparator: 'eq', value: literalValue('goal'), negate: false },
    ]
    expect(resultTypeStringFor(binding, [], attributeTypes)).toBe('entity[goal]')
  })

  it('formats an optional-cardinality connection binding with an open union', () => {
    const binding = mkQueryBinding()
    binding.name = 'maybe-link'
    binding.select = 'connections'
    binding.cardinality = 'optional'
    expect(resultTypeStringFor(binding, [], attributeTypes)).toBe('optional[connection[]]')
  })

  it('formats a projected set binding as list[scalar]', () => {
    const binding = mkQueryBinding()
    binding.name = 'scores'
    binding.cardinality = 'set'
    binding.project = 'risk_score'
    expect(resultTypeStringFor(binding, [], attributeTypes)).toBe('list[number]')
  })

  it('formats a count-aggregated binding as integer regardless of project', () => {
    const binding = mkQueryBinding()
    binding.name = 'count-of-things'
    binding.cardinality = 'set'
    binding.aggregate = 'count'
    expect(resultTypeStringFor(binding, [], attributeTypes)).toBe('integer')
  })

  it('formats a sum-aggregated projected binding as the projected scalar kind', () => {
    const binding = mkQueryBinding()
    binding.name = 'total-risk'
    binding.cardinality = 'set'
    binding.project = 'risk_score'
    binding.aggregate = 'sum'
    expect(resultTypeStringFor(binding, [], attributeTypes)).toBe('number')
  })

  it('formats a tuple binding from its referenced bindings own types', () => {
    const first = mkQueryBinding()
    first.name = 'a'
    first.cardinality = 'instance'
    const second = mkQueryBinding()
    second.name = 'b'
    second.cardinality = 'set'
    second.select = 'connections'
    const tuple = mkQueryBinding()
    tuple.name = 'pair'
    tuple.mode = 'tuple'
    tuple.tupleOf = ['a', 'b']
    expect(resultTypeStringFor(tuple, [first, second, tuple], attributeTypes)).toBe('tuple[entity[], connections[]]')
  })
})

describe('derivedOfStringFor / derivedOfFromString', () => {
  it('round-trips a connection.<attr> source', () => {
    const attribute = mkDerivedAttribute()
    attribute.ofHead = 'connection'
    attribute.ofAttribute = 'strength'
    const of = derivedOfStringFor(attribute)
    expect(of).toBe('connection.strength')
    expect(derivedOfFromString(of)).toEqual({ head: 'connection', attribute: 'strength' })
  })

  it('round-trips relationship.hops with no attribute', () => {
    const attribute = mkDerivedAttribute()
    attribute.ofHead = 'relationship-hops'
    const of = derivedOfStringFor(attribute)
    expect(of).toBe('relationship.hops')
    expect(derivedOfFromString(of)).toEqual({ head: 'relationship-hops', attribute: null })
  })

  it('is null when ofHead is none (legal only alongside reduce: count)', () => {
    expect(derivedOfStringFor(mkDerivedAttribute())).toBeNull()
    expect(derivedOfFromString(null)).toEqual({ head: 'none', attribute: null })
  })
})
