/**
 * The lab paints as the composer does — a box and its contents as one unit — and brings the unit holding
 * what was last pressed in front of its siblings.
 */
import { describe, expect, it } from 'vitest'
import type { Extent } from '../../../domain/layout/geometry'
import type { LabGeometry } from '../../../domain/layout/lab/labGeometry'
import { routingBandOf } from '../../../domain/layout/lab/labRouting'
import { SHAPE_DRAWING } from '../../../domain/layout/lab/__tests__/labDrawingFixtures'
import { dragRegionOf, handlesOf, paintOrder, pointsAttribute } from './labDrawing'

const at = (left: number, top: number, right: number, bottom: number): Extent => ({ left, top, right, bottom })

const box = (alias: string, inside: string | null) => ({
  alias, kind: 'domain' as const, section: 'boxes' as const, key: null, label: alias,
  extent: at(0, 0, 10, 10), inside, words: [], title_band: null, drawing: SHAPE_DRAWING,
})
const element = (alias: string, inside: string | null) => ({
  alias, key: null, label: alias, extent: at(0, 0, 10, 10), inside, words: [], outside_label: null, drawing: SHAPE_DRAWING,
})

const geometry: LabGeometry = {
  artifact_id: 'ARC@1.a.test', name: 'Test', canvas: at(0, 0, 100, 100), backdrop: [],
  boxes: [box('One', null), box('Two', null), box('Inner', 'One')],
  elements: [element('a', 'Inner'), element('b', 'Two'), element('c', null)],
  relations: [],
}

describe('a grouping title band', () => {
  const titled = {
    ...box('G', null),
    extent: at(10, 10, 250, 90),
    words: [{ text: 'Group', x: 110, y: 25, width: 30 }],
    title_band: at(86, 10, 164, 28), drawing: SHAPE_DRAWING,
  }

  it('is a routing obstacle only as wide as its title', () => {
    expect(routingBandOf(titled, at(10, 40, 250, 120))).toEqual(at(86, 40, 164, 58))
  })

  it('is dragged by across the box full width', () => {
    const now = at(10, 40, 250, 120)
    const band = routingBandOf(titled, now) as Extent
    expect(dragRegionOf(now)).toEqual(now)
    expect(dragRegionOf(now).left).toBeLessThan(band.left)
    expect(dragRegionOf(now).right).toBeGreaterThan(band.right)
  })
})

describe('the lab drawing', () => {
  it('paints a box, then everything in it, siblings as drawn', () => {
    expect(paintOrder(geometry, null).map((shape) => shape.alias)).toEqual(['One', 'Inner', 'a', 'Two', 'b', 'c'])
  })

  it('brings the unit holding the last pressed shape in front of its siblings', () => {
    expect(paintOrder(geometry, 'a').map((shape) => shape.alias)).toEqual(['Two', 'b', 'c', 'One', 'Inner', 'a'])
  })

  it('puts a handle on every corner and side', () => {
    const handles = handlesOf(at(0, 0, 100, 50))
    expect(handles.find((one) => one.handle === 'se')?.at).toEqual({ x: 100, y: 50 })
    expect(handles.find((one) => one.handle === 'n')?.at).toEqual({ x: 50, y: 0 })
    expect(handles).toHaveLength(8)
  })

  it('writes a course as SVG points', () => {
    expect(pointsAttribute([{ x: 1, y: 2 }, { x: 3, y: 4 }])).toBe('1,2 3,4')
  })
})
