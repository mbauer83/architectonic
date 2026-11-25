/**
 * Stacking among siblings (02·7): to the front and to the back go past every sibling, a step goes past
 * the next sibling the shape overlaps; a box and its contents stay one unit; the stacking is written
 * into the layout by the keys the composer reads it by, read back, patched, and painted.
 */
import { describe, expect, it } from 'vitest'
import type { Extent } from '../geometry'
import type { LayoutGeometry } from '../../schemas/diagramLayoutGeometry'
import { arrangedBy, arrangedUnits, layoutOf, layoutPatchBetween, patchIsEmpty } from '../arrangementLayout'
import { drawnArrangement, moved } from '../lab/labArrangement'
import { placementOf } from '../lab/labRouting'
import { LINE_DRAWING, SHAPE_DRAWING } from '../lab/__tests__/labDrawingFixtures'
import { restacked, stackedSiblings } from '../stacking'

const at = (left: number, top: number, right: number, bottom: number): Extent => ({ left, top, right, bottom })
const element = (alias: string, key: string, extent: Extent, inside?: string) => ({
  alias, key, label: alias, extent, inside, words: [], outside_label: undefined, drawing: SHAPE_DRAWING,
})

/** a, b and c overlap one another in a row, d stands apart; a box G holds x and y. */
const geometry: LayoutGeometry = {
  artifact_id: 'ARC@1.a.test', name: 'Test', canvas: at(0, 0, 800, 400), backdrop: [],
  surround: { drawn: { left: 0, top: 0, right: 0, bottom: 0 }, parts: [] },
  elements: [
    element('a', 'APP@1.a', at(0, 0, 100, 50)),
    element('b', 'APP@2.b', at(80, 10, 180, 60)),
    element('c', 'APP@3.c', at(160, 20, 260, 70)),
    element('d', 'APP@4.d', at(600, 0, 700, 50)),
    element('x', 'APP@5.x', at(20, 220, 120, 260), 'G'),
    element('y', 'APP@6.y', at(100, 230, 200, 270), 'G'),
  ],
  boxes: [{
    alias: 'G', kind: 'authored-grouping', section: 'boxes', key: 'g-1', label: 'Group',
    extent: at(10, 200, 210, 280), inside: undefined, words: [], title_band: undefined, drawing: SHAPE_DRAWING,
  }],
  relations: [{
    index: 0, key: 'r', source: 'a', target: 'd', decorated: [false, true],
    course: [[100, 25], [600, 25]], label: '', label_size: undefined, drawing: LINE_DRAWING,
  }],
}
const drawn = drawnArrangement(geometry)
const where = placementOf(geometry, drawn)
/** The canvas's own shapes back to front; as drawn, the box comes first. */
const top = (z: ReadonlyMap<string, number> | undefined) => stackedSiblings(['G', 'a', 'b', 'c', 'd'], z)

describe('restacking', () => {
  it('sends a shape to the front or the back of all its siblings', () => {
    expect(top(restacked(geometry, drawn, where, ['a'], 'front').z)).toEqual(['G', 'b', 'c', 'd', 'a'])
    expect(top(restacked(geometry, drawn, where, ['G'], 'front').z)).toEqual(['a', 'b', 'c', 'd', 'G'])
    expect(top(restacked(geometry, drawn, where, ['c'], 'back').z)).toEqual(['c', 'G', 'a', 'b', 'd'])
  })

  it('steps past the next sibling it overlaps, never past one it does not touch', () => {
    expect(top(restacked(geometry, drawn, where, ['a'], 'forward').z)).toEqual(['G', 'b', 'a', 'c', 'd'])
    expect(top(restacked(geometry, drawn, where, ['c'], 'backward').z)).toEqual(['G', 'a', 'c', 'b', 'd'])
    // d overlaps nothing: a step leaves the arrangement as it was.
    expect(restacked(geometry, drawn, where, ['d'], 'forward')).toBe(drawn)
    expect(restacked(geometry, drawn, where, ['c'], 'front').z?.size ?? 0).toBeGreaterThan(0)
  })

  it('keeps a selection in its own order when it goes to an end', () => {
    expect(top(restacked(geometry, drawn, where, ['a', 'b'], 'front').z)).toEqual(['G', 'c', 'd', 'a', 'b'])
    expect(top(restacked(geometry, drawn, where, ['b', 'c'], 'back').z)).toEqual(['b', 'c', 'G', 'a', 'd'])
  })

  it('restacks among siblings only: a box and its contents are one unit', () => {
    const inBox = restacked(geometry, drawn, where, ['x'], 'front')
    expect(stackedSiblings(['x', 'y'], inBox.z)).toEqual(['y', 'x'])
    expect(top(inBox.z)).toEqual(['G', 'a', 'b', 'c', 'd'])
  })

  it('survives a move, which carries the stacking along', () => {
    const now = moved(geometry, restacked(geometry, drawn, where, ['a'], 'front'), 'b', 5, 5)
    expect(top(now.z)).toEqual(['G', 'b', 'c', 'd', 'a'])
  })
})

describe('the stacking in the layout', () => {
  it('is written by the keys the composer reads it by, and read back to the same order', () => {
    const now = restacked(geometry, drawn, where, ['G'], 'front')
    const written = layoutOf(geometry, now)
    expect(written.z?.['g-1']).toBe(4)
    expect(written.z?.['APP@1.a']).toBe(0)
    expect(top(arrangedBy(geometry, written).z)).toEqual(top(now.z))
  })

  it('is patched like any other section, and counts as arranging the shapes it moved', () => {
    const now = restacked(geometry, drawn, where, ['a'], 'front')
    const patch = layoutPatchBetween({}, layoutOf(geometry, now))
    expect(patch.z['APP@1.a']).toEqual({ value: 4, based_on: null })
    expect(patchIsEmpty(layoutPatchBetween(layoutOf(geometry, now), layoutOf(geometry, now)))).toBe(true)
    expect(arrangedUnits(geometry, drawn, now)).toContain('a')
  })
})
