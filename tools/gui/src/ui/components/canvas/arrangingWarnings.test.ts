import { describe, expect, it } from 'vitest'
import type { Extent } from '../../../domain/layout/geometry'
import { hiddenElements, overlappingEnds } from './arrangingWarnings'

const at = (left: number, top: number, right: number, bottom: number): Extent => ({ left, top, right, bottom })

describe('an element hidden on the canvas', () => {
  const insideOf = new Map<string, string | undefined>([
    ['G', undefined], ['A', 'G'], ['H', undefined], ['C', undefined],
  ])
  const placement = {
    elements: new Map([['A', at(20, 20, 60, 40)], ['C', at(300, 20, 340, 40)]]),
    boxes: new Map([['G', at(0, 0, 100, 100)], ['H', at(50, 10, 200, 90)]]),
  }

  it('is one a box painted after it covers, named as what hides it, but not the box that holds it', () => {
    expect(hiddenElements(['G', 'A', 'H', 'C'], placement, insideOf)).toEqual([{ alias: 'A', by: 'H' }])
    expect(hiddenElements(['H', 'G', 'A', 'C'], placement, insideOf)).toEqual([])
  })
})

describe('connected elements over each other', () => {
  it('are named once per relation', () => {
    const breach = (relation: number, rule: 'ends-overlap' | 'jog') =>
      ({ relation, rule, tier: 'hard' as const, at: [] })
    expect([...overlappingEnds([breach(1, 'ends-overlap'), breach(1, 'ends-overlap'), breach(2, 'jog')])]).toEqual([1])
  })
})
