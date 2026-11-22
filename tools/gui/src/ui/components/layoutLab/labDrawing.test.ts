/**
 * Where the lab takes a shape to drag it, where its handles sit, and how it marks a breach. The order it
 * paints in is `labPaintOrder.test.ts`.
 */
import { describe, expect, it } from 'vitest'
import type { Extent } from '../../../domain/layout/geometry'
import { routingBandOf } from '../../../domain/layout/lab/labRouting'
import { SHAPE_DRAWING } from '../../../domain/layout/lab/__tests__/labDrawingFixtures'
import { breachMarksOf, dragRegionOf, handlesOf, pointsAttribute } from './labDrawing'

const at = (left: number, top: number, right: number, bottom: number): Extent => ({ left, top, right, bottom })

const box = (alias: string, inside: string | null) => ({
  alias, kind: 'domain' as const, section: 'boxes' as const, key: null, label: alias,
  extent: at(0, 0, 10, 10), inside, words: [], title_band: null, drawing: SHAPE_DRAWING,
})

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

describe('a breach mark', () => {
  const ends = [at(0, 0, 50, 20), at(100, 0, 150, 20)]
  const endsOf = () => ends

  /** Tags 10 units tall: each sits half its height above the point it names. */
  const SIZE = 10

  it('tags a stretch with the rule it breaks, just above the middle of the stretch', () => {
    const [mark] = breachMarksOf(
      [{ relation: 0, rule: 'jog', tier: 'soft', at: [{ x: 10, y: 10 }, { x: 10, y: 30 }] }], endsOf, SIZE)
    expect(mark.tag).toBe('jog')
    expect(mark.tagAt).toEqual({ x: 10, y: 15 })
    expect(mark.frames).toEqual([])
  })

  it('names a rule in words', () => {
    expect(breachMarksOf([{ relation: 0, rule: 'bend-at-an-end', tier: 'hard', at: [] }], endsOf, SIZE)[0].tag)
      .toBe('bend at an end')
  })

  it('frames both ends of a breach of the whole relation, tagged at the first', () => {
    const [mark] = breachMarksOf([{ relation: 0, rule: 'ends-overlap', tier: 'hard', at: [] }], endsOf, SIZE)
    expect(mark.frames).toEqual(ends)
    expect(mark.tagAt).toEqual({ x: 0, y: -5 })
  })

  it('marks a breach found twice over the same stretch once, and moves a second tag clear of the first', () => {
    const twice = [{ x: 0, y: 0 }, { x: 40, y: 0 }]
    const marks = breachMarksOf([
      { relation: 3, rule: 'text', tier: 'hard', at: twice },
      { relation: 3, rule: 'text', tier: 'hard', at: twice },
      { relation: 3, rule: 'jog', tier: 'soft', at: twice },
    ], endsOf, SIZE)
    expect(marks.map((mark) => mark.tag)).toEqual(['text', 'jog'])
    expect(marks[0].tagAt).toEqual({ x: 20, y: -5 })
    expect(marks[1].tagAt?.x).toBe(20)
    expect(Math.abs((marks[1].tagAt?.y ?? 0) - -5)).toBeGreaterThanOrEqual(SIZE)
  })

  it('shows the same tag once where two breaches of it lie close together, and marks both', () => {
    const marks = breachMarksOf([
      { relation: 1, rule: 'runs-along', tier: 'hard', at: [{ x: 0, y: 0 }, { x: 30, y: 0 }] },
      { relation: 2, rule: 'runs-along', tier: 'hard', at: [{ x: 0, y: 4 }, { x: 30, y: 4 }] },
      { relation: 3, rule: 'runs-along', tier: 'hard', at: [{ x: 500, y: 4 }, { x: 530, y: 4 }] },
    ], endsOf, SIZE)
    expect(marks).toHaveLength(3)
    expect(marks.map((mark) => mark.tagAt !== null)).toEqual([true, false, true])
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
