/**
 * What a selection rectangle chooses, and align and distribute applied to a selection: elements only,
 * each carrying what it holds, a box chosen only when wholly enclosed.
 */
import { describe, expect, it } from 'vitest'
import type { Extent } from '../geometry'
import type { LayoutGeometry } from '../../schemas/diagramLayoutGeometry'
import { drawnArrangement, movedTogether, placedAt } from '../canvasArrangement'
import { placementOf } from '../canvasRouting'
import {
  alignedSelection, bendsWithin, chosenBy, distributedSelection, toggled, withBends, withBendsMoved, withoutBends,
} from '../canvasSelection'
import { LINE_DRAWING } from './canvasDrawingFixtures'
import { extentAround } from '../geometry'
import { SHAPE_DRAWING } from './canvasDrawingFixtures'

const at = (left: number, top: number, right: number, bottom: number): Extent => ({ left, top, right, bottom })
const element = (alias: string, extent: Extent, inside?: string) =>
  ({
    alias, key: `APP@1.${alias}`, label: alias, extent, inside, words: [], outside_label: undefined,
    drawing: SHAPE_DRAWING,
  })

/** A and B in box G; C and D outside it, D with E drawn inside it. */
const geometry: LayoutGeometry = {
  artifact_id: 'ARC@1.a.test', name: 'Test', canvas: at(0, 0, 800, 400), backdrop: [],
  surround: { drawn: { left: 0, top: 0, right: 0, bottom: 0 }, parts: [] },
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

describe('the bends a selection rectangle picks up (sketch 02·8)', () => {
  /** C to D, its line bent twice; A to B inside the box, bent once. */
  const lines: LayoutGeometry = {
    ...geometry,
    relations: [
      { index: 0, key: 'cd', source: 'C', target: 'D', decorated: [false, true], course: [[500, 55], [600, 150]],
        label: '', label_size: undefined, drawing: LINE_DRAWING },
      { index: 1, key: 'ab', source: 'A', target: 'B', decorated: [false, true], course: [[120, 60], [140, 70]],
        label: '', label_size: undefined, drawing: LINE_DRAWING },
    ],
  }
  const bent = {
    ...start,
    routes: new Map([['cd', { via: [[550, 55], [550, 150]] as const }], ['ab', { via: [[130, 60]] as const }]]),
  }

  it('are the stated bends inside it, whatever the rectangle rule', () => {
    expect(bendsWithin(at(540, 40, 560, 100), bent.routes)).toEqual([{ key: 'cd', index: 0 }])
    expect(bendsWithin(at(0, 0, 800, 400), bent.routes)).toHaveLength(3)
    expect(withBends([{ key: 'cd', index: 0 }], [{ key: 'cd', index: 0 }, { key: 'ab', index: 0 }]))
      .toEqual([{ key: 'cd', index: 0 }, { key: 'ab', index: 0 }])
  })

  it('move with the selection, except on a line the selection carries whole', () => {
    const picked = [{ key: 'cd', index: 1 }, { key: 'ab', index: 0 }]
    const moved = withBendsMoved(lines, bent, picked, ['G'], 10, 5)
    expect(moved.routes.get('cd')?.via).toEqual([[550, 55], [560, 155]])
    expect(moved.routes.get('ab')?.via).toEqual([[130, 60]])
  })

  it('go when the selection is removed, each line keeping its other bends', () => {
    const left = withoutBends(bent, [{ key: 'cd', index: 0 }])
    expect(left.routes.get('cd')?.via).toEqual([[550, 150]])
    expect(withoutBends(left, [{ key: 'ab', index: 0 }]).routes.get('ab')?.via).toBeUndefined()
  })
})
