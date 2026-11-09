/**
 * A free exploration draws the relations of what was explored, and the ones among its neighbours only
 * on request.
 */
import { describe, expect, it } from 'vitest'
import { explorationFocus, relationsOfFocus } from '../focusRelations'

const node = (id: string, expanded = false) => ({ id, expanded })
const relation = (source: string, target: string) => ({ source, target })

describe('explorationFocus', () => {
  it('is the root and every expanded node', () => {
    const focus = explorationFocus('root', [node('root', true), node('a', true), node('b')])
    expect([...focus].sort()).toEqual(['a', 'root'])
  })

  it('holds the root before its first hop has been marked expanded', () => {
    expect([...explorationFocus('root', [])]).toEqual(['root'])
  })

  it('is empty on the unanchored route, which has no root', () => {
    expect(explorationFocus('', []).size).toBe(0)
  })
})

describe('relationsOfFocus', () => {
  const relations = [relation('root', 'a'), relation('b', 'root'), relation('a', 'b'), relation('b', 'c')]

  it('keeps the relations of the focus in either direction, and drops those between neighbours', () => {
    expect(relationsOfFocus(relations, new Set(['root'])))
      .toEqual([relation('root', 'a'), relation('b', 'root')])
  })

  it('treats an expanded neighbour as focus, so its own relations appear', () => {
    expect(relationsOfFocus(relations, new Set(['root', 'b'])))
      .toEqual([relation('root', 'a'), relation('b', 'root'), relation('a', 'b'), relation('b', 'c')])
  })
})
