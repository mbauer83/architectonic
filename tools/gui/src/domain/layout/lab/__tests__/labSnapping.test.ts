/**
 * Where a moved or resized shape lands (sketch 02·1, 02·2, 04·4): on the 8 px grid, or on a neighbour's
 * edge or centre within the tolerance, with a dashed guide across both; never snapping in hints mode;
 * never aligning to what moves with it, to a box that holds it, or to a neighbour out of reach.
 */
import { describe, expect, it } from 'vitest'
import type { Extent } from '../../geometry'
import type { LayoutGeometry } from '../../../schemas/diagramLayoutGeometry'
import { GRID, NEIGHBOUR_REACH, inLineGuide, movingLinesOf, neighboursOf, snapped } from '../labSnapping'
import { SHAPE_DRAWING } from './labDrawingFixtures'

const at = (left: number, top: number, right: number, bottom: number): Extent => ({ left, top, right, bottom })
const MOVE = movingLinesOf(null)

describe('a move lands on the grid', () => {
  it('rounds its top-left corner to the 8 px grid when nothing lines up', () => {
    const result = snapped(at(13, 21, 113, 61), MOVE, [], 6, 'snap')
    expect([13 + result.dx, 21 + result.dy]).toEqual([16, 24])
    expect((13 + result.dx) % GRID).toBe(0)
    expect(result.guides).toEqual([])
  })

  it('stays where it was reached when guides are only hints', () => {
    expect(snapped(at(13, 21, 113, 61), MOVE, [], 6, 'hints')).toEqual({ dx: 0, dy: 0, guides: [] })
  })
})

describe('a move aligns to a neighbour', () => {
  const neighbour = at(200, 100, 300, 140)

  it('snaps its top edge onto the neighbour top within the tolerance, with a horizontal guide', () => {
    const result = snapped(at(13, 104, 113, 144), MOVE, [neighbour], 6, 'snap')
    expect(result.dy).toBe(-4)
    expect(result.guides).toEqual([{ axis: 'y', at: 100, from: 13 + result.dx - 8, to: 308 }])
  })

  it('aligns centres as well as edges', () => {
    // centre y 122 against the neighbour centre 120
    const result = snapped(at(13, 102, 113, 142), MOVE, [neighbour], 6, 'snap')
    expect(result.dy).toBe(-2)
    expect(result.guides[0]).toMatchObject({ axis: 'y', at: 100 })
  })

  it('takes the nearest of several lines that are within reach', () => {
    const result = snapped(at(196, 300, 296, 340), MOVE, [neighbour, at(199, 0, 220, 20)], 6, 'snap')
    expect(result.dx).toBe(3)
    expect(result.guides[0]).toMatchObject({ axis: 'x', at: 199 })
  })

  it('ignores a neighbour line beyond the tolerance and falls back to the grid', () => {
    const result = snapped(at(13, 110, 113, 150), MOVE, [neighbour], 6, 'snap')
    expect([result.dy, result.guides.length]).toEqual([2, 0])
  })

  it('shows the guide but does not move the shape when guides are hints', () => {
    const result = snapped(at(13, 104, 113, 144), MOVE, [neighbour], 6, 'hints')
    expect([result.dx, result.dy]).toEqual([0, 0])
    expect(result.guides).toEqual([{ axis: 'y', at: 100, from: 5, to: 308 }])
  })
})

describe('a resize aligns only the edge being dragged', () => {
  const neighbour = at(200, 100, 300, 140)

  it('snaps a dragged right edge onto a neighbour left edge', () => {
    const result = snapped(at(10, 10, 197, 50), movingLinesOf('e'), [neighbour], 6, 'snap')
    expect([result.dx, result.dy]).toEqual([3, 0])
    expect(result.guides).toHaveLength(1)
  })

  it('leaves an axis whose edges the handle does not drag', () => {
    expect(movingLinesOf('e')).toEqual({ x: ['high'], y: [] })
    expect(movingLinesOf('nw')).toEqual({ x: ['low'], y: ['low'] })
    expect(snapped(at(10, 103, 197, 50), movingLinesOf('e'), [neighbour], 6, 'snap').dy).toBe(0)
  })

  it('grids a dragged edge when nothing lines up', () => {
    const result = snapped(at(10, 10, 61, 50), movingLinesOf('se'), [], 6, 'snap')
    expect([61 + result.dx, 50 + result.dy]).toEqual([64, 48])
  })
})

describe('what a shape may align to', () => {
  const geometry: LayoutGeometry = {
    artifact_id: 'ARC@1.a.test', name: 'Test', canvas: at(0, 0, 4000, 400), backdrop: [],
    surround: { drawn: { left: 0, top: 0, right: 0, bottom: 0 }, parts: [] },
    elements: [
      { alias: 'A', label: 'A', extent: at(20, 40, 120, 80), inside: 'G', words: [], drawing: SHAPE_DRAWING },
      { alias: 'B', label: 'B', extent: at(140, 40, 240, 80), inside: 'G', words: [], drawing: SHAPE_DRAWING },
      { alias: 'C', label: 'C', extent: at(400, 40, 500, 80), words: [], drawing: SHAPE_DRAWING },
      { alias: 'F', label: 'F', extent: at(3000, 40, 3100, 80), words: [], drawing: SHAPE_DRAWING },
    ],
    boxes: [{
      alias: 'G', kind: 'authored-grouping', section: 'boxes', label: 'Group', extent: at(10, 10, 250, 90),
      words: [], drawing: SHAPE_DRAWING,
    }],
    relations: [],
  }
  const placement = {
    elements: new Map(geometry.elements.map((one) => [one.alias, one.extent])),
    boxes: new Map(geometry.boxes.map((one) => [one.alias, one.extent])),
  }

  it('skips what moves, the box holding it, and a shape out of reach', () => {
    const found = neighboursOf(geometry, placement, ['A'], at(20, 40, 120, 80))
    expect(found).toEqual([at(140, 40, 240, 80), at(400, 40, 500, 80)])
    expect(3000 - 20).toBeGreaterThan(NEIGHBOUR_REACH)
  })

  it('skips what a moved box carries, and keeps the other boxes', () => {
    const found = neighboursOf(geometry, placement, ['G'], at(10, 10, 250, 90))
    expect(found).toEqual([at(400, 40, 500, 80)])
    expect(neighboursOf(geometry, placement, ['C'], at(400, 40, 500, 80))).toContainEqual(at(10, 10, 250, 90))
  })
})

describe('a line end in line with the other end', () => {
  const extent = at(100, 100, 200, 140)

  it('shows a guide along the run when the end lies level with the other end', () => {
    expect(inLineGuide(extent, { side: 'right', at: 0.5 }, { x: 400, y: 120 }))
      .toEqual({ axis: 'y', at: 120, from: 200, to: 400 })
    expect(inLineGuide(extent, { side: 'top', at: 0.25 }, { x: 125, y: 0 }))
      .toEqual({ axis: 'x', at: 125, from: 0, to: 100 })
  })

  it('shows none where the end is not in line', () => {
    expect(inLineGuide(extent, { side: 'right', at: 0.5 }, { x: 400, y: 130 })).toBeNull()
    expect(inLineGuide(extent, { side: 'right', at: 0.5 }, null)).toBeNull()
  })
})
