/**
 * An arrangement written down and read back agree; the patch between two layouts changes only what
 * differs, each entry checked against what was read; and an edit counts what it arranged, a box moved
 * with its contents being one change.
 */
import { describe, expect, it } from 'vitest'
import type { Extent } from '../geometry'
import type { LayoutGeometry } from '../../schemas/diagramLayoutGeometry'
import { arrangedBy, arrangedUnits, layoutOf, layoutPatchBetween, patchIsEmpty } from '../arrangementLayout'
import { drawnArrangement, moved, resized } from '../lab/labArrangement'
import { placementOf } from '../lab/labRouting'
import { LINE_DRAWING, SHAPE_DRAWING } from '../lab/__tests__/labDrawingFixtures'

const at = (left: number, top: number, right: number, bottom: number): Extent => ({ left, top, right, bottom })

const element = (alias: string, key: string, extent: Extent, inside?: string) => ({
  alias, key, label: alias, extent, inside, words: [], outside_label: undefined, drawing: SHAPE_DRAWING,
})

/** A grouping holding two elements, and one element outside it. */
const geometry: LayoutGeometry = {
  artifact_id: 'ARC@1.a.test',
  name: 'Test',
  canvas: at(0, 0, 600, 400),
  backdrop: [],
  elements: [
    element('A', 'APP@1.a', at(20, 40, 120, 80), 'G'),
    element('B', 'APP@2.b', at(140, 40, 240, 80), 'G'),
    element('C', 'APP@3.c', at(400, 40, 500, 80)),
  ],
  boxes: [{
    alias: 'G', kind: 'authored-grouping', section: 'boxes', key: 'g-1', label: 'Group',
    extent: at(10, 10, 250, 90), inside: undefined, words: [], title_band: at(86, 10, 164, 28),
    drawing: SHAPE_DRAWING,
  }],
  relations: [{
    index: 0, key: 'r', source: 'B', target: 'C', decorated: [false, true],
    course: [[240, 60], [400, 60]], label: '', label_size: undefined, drawing: LINE_DRAWING,
  }],
}

const drawn = drawnArrangement(geometry)

describe('a layout written down and read back', () => {
  it('places every shape where the arrangement had it', () => {
    const arranged = resized(geometry, moved(geometry, drawn, 'C', 30, 20), 'A', at(20, 40, 160, 90))
    const back = arrangedBy(geometry, layoutOf(geometry, arranged))
    expect(placementOf(geometry, back)).toEqual(placementOf(geometry, arranged))
  })

  it('states a size only for an element that was resized', () => {
    const written = layoutOf(geometry, resized(geometry, drawn, 'A', at(20, 40, 160, 90)))
    expect(written.elements['APP@1.a']).toEqual({ x: 20, y: 40, w: 140, h: 50 })
    expect(written.elements['APP@3.c']).toEqual({ x: 400, y: 40 })
    expect(written.boxes['g-1']).toMatchObject({ x: 10, y: 10 })
  })
})

describe('the patch between two layouts', () => {
  it('changes only what differs, each entry read as what was stored', () => {
    const stored = layoutOf(geometry, drawn)
    const wanted = layoutOf(geometry, moved(geometry, drawn, 'C', 30, 20))
    const patch = layoutPatchBetween(stored, wanted)
    expect(patch.elements).toEqual({
      'APP@3.c': { value: { x: 430, y: 60 }, based_on: { x: 400, y: 40 } },
    })
    expect(patch.boxes).toEqual({})
  })

  it('removes every stored entry when the diagram returns to automatic', () => {
    const stored = layoutOf(geometry, drawn)
    const patch = layoutPatchBetween(stored, null)
    expect(Object.values(patch.elements).every((change) => change.value === null)).toBe(true)
    expect(Object.keys(patch.elements)).toHaveLength(3)
    expect(patchIsEmpty(layoutPatchBetween(stored, stored))).toBe(true)
  })
})

describe('what an edit arranged', () => {
  it('counts a moved element once', () => {
    expect(arrangedUnits(geometry, drawn, moved(geometry, drawn, 'C', 30, 20))).toEqual(['C'])
  })

  it('counts a box moved with its contents as one change', () => {
    expect(arrangedUnits(geometry, drawn, moved(geometry, drawn, 'G', 0, 50))).toEqual(['G'])
  })

  it('does not count a box that only grew round a moved member', () => {
    expect(arrangedUnits(geometry, drawn, moved(geometry, drawn, 'A', -5, 30))).toEqual(['A'])
  })

  it('counts nothing once a move is undone', () => {
    const there = moved(geometry, drawn, 'C', 30, 20)
    expect(arrangedUnits(geometry, drawn, moved(geometry, there, 'C', -30, -20))).toEqual([])
  })
})
