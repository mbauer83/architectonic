/**
 * What a selection rectangle chooses, and align and distribute applied to a selection: elements only,
 * each carrying what it holds, a box chosen only when wholly enclosed.
 */
import { describe, expect, it } from 'vitest'
import type { Extent } from '../../geometry'
import type { LayoutGeometry } from '../../../schemas/diagramLayoutGeometry'
import { drawnArrangement, movedTogether, placedAt } from '../labArrangement'
import { placementOf } from '../labRouting'
import { alignedSelection, chosenBy, distributedSelection, toggled } from '../labSelection'
import { extentAround } from '../../geometry'
import { SHAPE_DRAWING } from './labDrawingFixtures'

const at = (left: number, top: number, right: number, bottom: number): Extent => ({ left, top, right, bottom })
const element = (alias: string, extent: Extent, inside?: string) =>
  ({ alias, key: `APP@1.${alias}`, label: alias, extent, inside, words: [], outside_label: undefined, drawing: SHAPE_DRAWING })

/** A and B in box G; C and D outside it, D with E drawn inside it. */
const geometry: LayoutGeometry = {
  artifact_id: 'ARC@1.a.test', name: 'Test', canvas: at(0, 0, 800, 400), backdrop: [],
  elements: [
    element('A', at(20, 40, 120, 80), 'G'), element('B', at(140, 50, 240, 90), 'G'),
    element('C', at(400, 40, 500, 70)), element('D', at(600, 100, 700, 200)), element('E', at(620, 140, 660, 180), 'D'),
  ],
  boxes: [{
    alias: 'G', kind: 'authored-grouping', section: 'boxes', key: 'g-1', label: 'G',
    extent: at(10, 10, 250, 100), inside: undefined, words: [], title_band: undefined, drawing: SHAPE_DRAWING,
  }],
  relations: [],
}
const start = drawnArrangement(geometry)
const placement = placementOf(geometry, start)

describe('a selection rectangle', () => {
  it('spans its two corners whichever way it was drawn', () => {
    expect(extentAround([{ x: 50, y: 90 }, { x: 10, y: 20 }])).toEqual(at(10, 20, 50, 90))
    expect(extentAround([])).toBeNull()
  })

  it('chooses the elements it encloses, and a box only when wholly inside it', () => {
    expect(chosenBy(at(15, 30, 510, 95), placement)).toEqual(['A', 'B', 'C'])
    expect(chosenBy(at(0, 0, 260, 110), placement)).toEqual(['A', 'B', 'G'])
  })

  it('chooses every element it touches when the preference says so, but never a box only touched', () => {
    expect(chosenBy(at(100, 60, 410, 65), placement, 'touches')).toEqual(['A', 'B', 'C'])
  })
})

describe('toggling', () => {
  it('takes out what is in and adds what is not', () => {
    expect(toggled(['A', 'B'], 'A')).toEqual(['B'])
    expect(toggled(['B'], 'C')).toEqual(['B', 'C'])
  })
})

describe('moving several together', () => {
  it('moves a shape both chosen and carried by a box once', () => {
    const next = movedTogether(geometry, start, ['G', 'A'], 10, 0)
    expect(next.elements.get('A')).toEqual(at(30, 40, 130, 80))
    expect(next.elements.get('C')).toEqual(at(400, 40, 500, 70))
  })

  it('places an element by its top-left corner, carrying what it holds', () => {
    const next = placedAt(geometry, start, new Map([['D', { x: 500, y: 100 }]]))
    expect(next.elements.get('E')).toEqual(at(520, 140, 560, 180))
  })
})

describe('align and distribute on a selection', () => {
  it('aligns the elements and passes over a box', () => {
    const next = alignedSelection(geometry, start, placement, ['A', 'C', 'G'], 'top')
    expect(next.elements.get('C')).toEqual(at(400, 40, 500, 70))
    expect(alignedSelection(geometry, start, placement, ['B', 'C'], 'bottom').elements.get('C'))
      .toEqual(at(400, 60, 500, 90))
  })

  it('leaves the arrangement as it was when too few are elements', () => {
    expect(alignedSelection(geometry, start, placement, ['A', 'G'], 'left')).toBe(start)
    expect(distributedSelection(geometry, start, placement, ['A', 'B', 'G'], 'x')).toBe(start)
  })

  it('distributes with equal gaps, the outer two kept, an element carrying what it holds', () => {
    const next = distributedSelection(geometry, start, placement, ['D', 'A', 'C'], 'x')
    expect(next.elements.get('A')).toEqual(at(20, 40, 120, 80))
    expect(next.elements.get('D')).toEqual(at(600, 100, 700, 200))
    expect(next.elements.get('C')).toEqual(at(310, 40, 410, 70))
    expect(next.elements.get('E')).toEqual(at(620, 140, 660, 180))
  })
})
