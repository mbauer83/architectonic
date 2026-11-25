/**
 * Where the canvas takes a shape to drag it, where its handles sit, and how it marks a breach. The order it
 * paints in is `labPaintOrder.test.ts`.
 */
import { describe, expect, it } from 'vitest'
import type { Extent } from '../../../domain/layout/geometry'
import { routingBandOf } from '../../../domain/layout/lab/labRouting'
import { SHAPE_DRAWING } from '../../../domain/layout/lab/__tests__/labDrawingFixtures'
import { breachMarksOf, dragRegionOf, handlesOf, pointsAttribute } from './labDrawing'

const at = (left: number, top: number, right: number, bottom: number): Extent => ({ left, top, right, bottom })

const box = (alias: string, inside?: string) => ({
  alias, kind: 'domain' as const, section: 'boxes' as const, key: undefined, label: alias,
  extent: at(0, 0, 10, 10), inside, words: [], title_band: undefined, drawing: SHAPE_DRAWING,
})

describe('a grouping title band', () => {
  const titled = {
    ...box('G', undefined),
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
    const region = dragRegionOf(now, 18)
    expect(region).toEqual(at(10, 40, 250, 58))
    expect(region.left).toBeLessThan(band.left)
    expect(region.right).toBeGreaterThan(band.right)
  })

  it('leaves an element its whole outline to drag by', () => {
    expect(dragRegionOf(at(0, 0, 40, 20))).toEqual(at(0, 0, 40, 20))
  })
})

describe('a breach mark', () => {
  const ends = [at(0, 0, 50, 20), at(100, 0, 150, 20)]
  const endsOf = () => ends

  it('traces a stretch that breaks a rule, and frames nothing', () => {
    const [mark] = breachMarksOf([{ relation: 0, rule: 'jog', tier: 'soft', at: [{ x: 10, y: 10 }, { x: 10, y: 50 }] }], endsOf)
    expect(mark.frames).toEqual([])
  })

  it('frames both ends of a breach of the whole relation', () => {
    const [mark] = breachMarksOf([{ relation: 0, rule: 'ends-overlap', tier: 'hard', at: [] }], endsOf)
    expect(mark.frames).toEqual(ends)
  })

  it('marks a breach found twice over the same stretch once', () => {
    const twice = [{ x: 0, y: 0 }, { x: 40, y: 0 }]
    const marks = breachMarksOf([
      { relation: 3, rule: 'text', tier: 'hard', at: twice },
      { relation: 3, rule: 'text', tier: 'hard', at: twice },
      { relation: 3, rule: 'jog', tier: 'soft', at: twice },
    ], endsOf)
    expect(marks.map((mark) => mark.breach.rule)).toEqual(['text', 'jog'])
  })
})

describe('the canvas drawing', () => {
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
