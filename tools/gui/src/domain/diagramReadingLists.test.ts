import { describe, expect, it } from 'vitest'
import type { DerivedFrom, ModelRelation } from './diagramReadingLists'
import { derivedOf, notDrawnOf, reachShows } from './diagramReadingLists'

const relation = (id: string, source: string, target: string, conn_type = 'archimate-serving'): ModelRelation =>
  ({ artifact_id: id, source, target, source_name: source.toUpperCase(), target_name: target.toUpperCase(), conn_type })

const both = { incoming: 1, outgoing: 1 } as const

describe('which way a reach shows', () => {
  it('shows a direction only while its reach is on, and an undirected relation while either is', () => {
    expect(reachShows({ incoming: 0, outgoing: 2 }, 'incoming')).toBe(false)
    expect(reachShows({ incoming: 0, outgoing: 2 }, 'outgoing')).toBe(true)
    expect(reachShows({ incoming: 0, outgoing: 'all' }, 'undirected')).toBe(true)
    expect(reachShows({ incoming: 0, outgoing: 0 }, 'undirected')).toBe(false)
  })
})

describe('the relations the model has and the diagram does not draw', () => {
  const candidates = [
    relation('drawn', 'sel', 'x'), relation('out', 'sel', 'far'), relation('in', 'near', 'sel'),
    relation('assoc', 'sel', 'pal', 'archimate-association'), relation('elsewhere', 'a', 'b'),
  ]
  const input = {
    selection: ['sel'], candidates, drawnRelations: new Set(['drawn']), drawnEntities: new Set(['sel', 'near']),
    undirected: new Set(['archimate-association']), reach: both,
  }

  it('lists each undrawn relation of the selection once, by which way it runs and whether its end is drawn', () => {
    expect(notDrawnOf(input).map((row) => [row.id, row.way, row.other, row.otherDrawn, row.here])).toEqual([
      ['out', 'outgoing', 'far', false, 'sel'],
      ['in', 'incoming', 'near', true, 'sel'],
      ['assoc', 'undirected', 'pal', false, 'sel'],
    ])
    expect(notDrawnOf(input)[1].otherName).toBe('NEAR')
  })

  it('follows the reach: none incoming hides what leads here', () => {
    expect(notDrawnOf({ ...input, reach: { incoming: 0, outgoing: 1 } }).map((row) => row.id)).toEqual(['out', 'assoc'])
    expect(notDrawnOf({ ...input, reach: { incoming: 0, outgoing: 0 } })).toEqual([])
  })
})

describe('the relationships the model derives', () => {
  const row = (entity: string, certainty: string, hops: number, direction: 'outbound' | 'inbound' = 'outbound',
    type = 'archimate-serving'): DerivedFrom =>
    ({ entity_id: entity, entity_name: entity.toUpperCase(), type, direction, certainty, hops })

  it('splits by certainty, nearest first, and keeps the shortest of each end, type and way', () => {
    const derived = derivedOf(new Map([
      ['a', [row('z', 'potential', 3), row('y', 'certain', 2), row('z', 'potential', 2), row('x', 'certain', 2, 'inbound')]],
    ]), both, new Set())
    expect(derived.certain.map((one) => [one.entityId, one.way])).toEqual([['x', 'incoming'], ['y', 'outgoing']])
    expect(derived.potential).toEqual([{ entityId: 'z', name: 'Z', type: 'archimate-serving', way: 'outgoing', hops: 2 }])
  })

  it('prefers a certain derivation over a potential one, from whichever selected element it came', () => {
    const derived = derivedOf(new Map([['a', [row('z', 'potential', 2)]], ['b', [row('z', 'certain', 4)]]]), both, new Set())
    expect(derived.certain.map((one) => one.entityId)).toEqual(['z'])
    expect(derived.potential).toEqual([])
  })

  it('leaves out other selected elements, follows the reach, and gives an undirected type no way', () => {
    const derived = derivedOf(new Map([
      ['a', [row('b', 'certain', 2), row('in', 'certain', 2, 'inbound'), row('pal', 'certain', 2, 'inbound', 'assoc')]],
      ['b', []],
    ]), { incoming: 0, outgoing: 1 }, new Set(['assoc']))
    expect(derived.certain.map((one) => [one.entityId, one.way])).toEqual([['pal', 'undirected']])
  })
})
