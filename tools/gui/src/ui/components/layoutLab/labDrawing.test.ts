/**
 * Where the lab takes a shape to drag it, where its handles sit, and how it marks a breach. The order it
 * paints in is `labPaintOrder.test.ts`.
 */
import { describe, expect, it } from 'vitest'
import type { Extent } from '../../../domain/layout/geometry'
import { overlaps } from '../../../domain/layout/geometry'
import { routingBandOf } from '../../../domain/layout/lab/labRouting'
import { SHAPE_DRAWING } from '../../../domain/layout/lab/__tests__/labDrawingFixtures'
import type { BreachLabel } from './labDrawing'
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

  /** Tags 10 units tall. */
  const SIZE = 10

  /** Whether *extent* stays clear of every point within *margin* of the stretch from *from* to *to*. */
  const clearOf = (extent: Extent, from: { x: number; y: number }, to: { x: number; y: number }, margin: number) =>
    extent.right < Math.min(from.x, to.x) - margin || extent.left > Math.max(from.x, to.x) + margin
    || extent.bottom < Math.min(from.y, to.y) - margin || extent.top > Math.max(from.y, to.y) + margin

  it('sets the tag of a stretch that runs down beside it, off the line, with a leader to its middle', () => {
    const from = { x: 10, y: 10 }
    const to = { x: 10, y: 50 }
    const [mark] = breachMarksOf([{ relation: 0, rule: 'jog', tier: 'soft', at: [from, to] }], endsOf, SIZE)
    expect(mark.tag).toBe('jog')
    expect(mark.frames).toEqual([])
    const label = mark.label as BreachLabel
    expect(label.leader[1]).toEqual({ x: 10, y: 30 })
    expect(label.box.left).toBeGreaterThan(from.x)
    expect(clearOf(label.box, from, to, SIZE / 2)).toBe(true)
  })

  it('sets the tag of a stretch that runs across above it, off the line', () => {
    const from = { x: 0, y: 100 }
    const to = { x: 80, y: 100 }
    const [mark] = breachMarksOf([{ relation: 0, rule: 'runs-along', tier: 'hard', at: [from, to] }], endsOf, SIZE)
    const label = mark.label as BreachLabel
    expect(label.box.bottom).toBeLessThan(100)
    expect(clearOf(label.box, from, to, SIZE / 2)).toBe(true)
    expect(label.leader).toEqual([{ x: 40, y: label.box.bottom }, { x: 40, y: 100 }])
  })

  it('names a rule in words', () => {
    expect(breachMarksOf([{ relation: 0, rule: 'bend-at-an-end', tier: 'hard', at: [] }], endsOf, SIZE)[0].tag)
      .toBe('bend at an end')
  })

  it('frames both ends of a breach of the whole relation, tagged above the first', () => {
    const [mark] = breachMarksOf([{ relation: 0, rule: 'ends-overlap', tier: 'hard', at: [] }], endsOf, SIZE)
    expect(mark.frames).toEqual(ends)
    const label = mark.label as BreachLabel
    expect(label.box.bottom).toBeLessThan(0)
    expect(label.leader[1]).toEqual({ x: 0, y: 0 })
  })

  it('marks a breach found twice over the same stretch once, and moves a second tag clear of the first', () => {
    const twice = [{ x: 0, y: 0 }, { x: 40, y: 0 }]
    const marks = breachMarksOf([
      { relation: 3, rule: 'text', tier: 'hard', at: twice },
      { relation: 3, rule: 'text', tier: 'hard', at: twice },
      { relation: 3, rule: 'jog', tier: 'soft', at: twice },
    ], endsOf, SIZE)
    expect(marks.map((mark) => mark.tag)).toEqual(['text', 'jog'])
    const [first, second] = marks.map((mark) => mark.label as BreachLabel)
    expect(second.at.x).toBe(first.at.x)
    expect(overlaps(first.box, second.box)).toBe(false)
  })

  it('shows the same tag once where two breaches of it lie close together, and marks both', () => {
    const marks = breachMarksOf([
      { relation: 1, rule: 'runs-along', tier: 'hard', at: [{ x: 0, y: 0 }, { x: 30, y: 0 }] },
      { relation: 2, rule: 'runs-along', tier: 'hard', at: [{ x: 0, y: 4 }, { x: 30, y: 4 }] },
      { relation: 3, rule: 'runs-along', tier: 'hard', at: [{ x: 500, y: 4 }, { x: 530, y: 4 }] },
    ], endsOf, SIZE)
    expect(marks).toHaveLength(3)
    expect(marks.map((mark) => mark.label !== null)).toEqual([true, false, true])
  })
})

describe('the lab drawing', () => {
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
