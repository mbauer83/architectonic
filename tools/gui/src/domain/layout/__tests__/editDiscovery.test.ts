/**
 * What the edit panel offers (sketch 01·8): the model's relations between drawn elements that the
 * diagram does not draw, and elements told apart by whether the diagram draws them already.
 */
import { describe, expect, it } from 'vitest'
import { discovered, undrawnRelationsAmong } from '../editDiscovery'
import type { ModelRelation } from '../../diagramReadingLists'

const relation = (source: string, type: string, target: string): ModelRelation => ({
  artifact_id: `${source}---${target}@@${type}`, source, target, conn_type: type,
  source_name: source.toUpperCase(), target_name: target.toUpperCase(),
})

describe('relations in the model, not drawn', () => {
  const drawn = new Map([['APP@1.a', 'A'], ['APP@2.b', 'B']])

  it('lists one between two drawn elements, with the drawings of its ends, source first', () => {
    const rows = undrawnRelationsAmong([relation('APP@2.b.slug', 'archimate-serving', 'APP@1.a')], drawn, new Set())
    expect(rows).toEqual([{
      id: 'APP@2.b.slug---APP@1.a@@archimate-serving', type: 'archimate-serving', sourceName: 'APP@2.B.SLUG',
      targetName: 'APP@1.A', ends: ['B', 'A'],
    }])
  })

  it('leaves out one the session draws, one to an element not drawn, and a repeat', () => {
    const drawnOne = relation('APP@1.a', 'archimate-access', 'APP@2.b')
    const rows = undrawnRelationsAmong([
      drawnOne, relation('APP@1.a', 'archimate-flow', 'APP@9.z'),
      relation('APP@1.a', 'archimate-serving', 'APP@2.b'), relation('APP@1.a.slug', 'archimate-serving', 'APP@2.b'),
    ], drawn, new Set([drawnOne.artifact_id]))
    expect(rows.map((row) => row.type)).toEqual(['archimate-serving'])
  })
})

describe('elements the panel lists', () => {
  it('lists each once, marks the drawn ones with their drawing, and puts them after the rest', () => {
    const rows = discovered([
      { artifact_id: 'APP@1.a.portal' }, { artifact_id: 'APP@3.c' }, { artifact_id: 'APP@1.a' },
    ], new Map([['APP@1.a', 'A']]))
    expect(rows).toEqual([
      { entity: { artifact_id: 'APP@3.c' }, drawnAs: undefined },
      { entity: { artifact_id: 'APP@1.a' }, drawnAs: 'A' },
    ])
  })
})
