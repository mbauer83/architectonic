/**
 * The canvas counts each rule a line breaks, by the tier the rules state — not a tier of its own.
 */
import { describe, expect, it } from 'vitest'
import type { Extent, Point } from '../../geometry'
import { RULE_TIERS } from '../../routeQuality'
import { breachesOf, countByTier, tierOf } from '../labBreaches'
import { LINE_DRAWING, SHAPE_DRAWING } from './labDrawingFixtures'
import type { LayoutGeometry } from '../../../schemas/diagramLayoutGeometry'
import { fullPass, placementOf, textRegions } from '../labRouting'
import { drawnArrangement } from '../labArrangement'

const at = (left: number, top: number, right: number, bottom: number): Extent => ({ left, top, right, bottom })

const geometry: LayoutGeometry = {
  artifact_id: 'ARC@1.a.test',
  name: 'Test',
  canvas: at(0, 0, 600, 400),
  backdrop: [],
  surround: [],
  elements: [
    { alias: 'S', key: 'APP@1.s', label: 'S', extent: at(0, 100, 80, 140), inside: undefined, words: [], outside_label: undefined, drawing: SHAPE_DRAWING },
    { alias: 'T', key: 'APP@2.t', label: 'T', extent: at(400, 100, 480, 140), inside: undefined, words: [], outside_label: undefined, drawing: SHAPE_DRAWING },
    { alias: 'X', key: 'APP@3.x', label: 'X', extent: at(200, 90, 260, 150), inside: undefined, words: [], outside_label: undefined, drawing: SHAPE_DRAWING },
  ],
  boxes: [],
  relations: [
    { index: 0, key: 'r', source: 'S', target: 'T', decorated: [false, true], course: [], label: '', label_size: undefined, drawing: LINE_DRAWING },
  ],
}

const placement = placementOf(geometry, drawnArrangement(geometry))
const text = textRegions(geometry, placement)

describe('the canvas breaches', () => {
  it('takes the readability tiers from the rules as stated', () => {
    for (const [rule, tier] of Object.entries(RULE_TIERS)) {
      if (rule === 'text' || rule === 'bend-at-an-end' || rule === 'runs-along' || rule === 'jog') {
        expect(tierOf(rule)).toBe(tier)
      }
    }
    expect(tierOf('crosses-an-element')).toBe('hard')
    expect(tierOf('unroutable')).toBe('hard')
  })

  it('reports a line straight through another element as hard', () => {
    const through: Point[] = [{ x: 80, y: 120 }, { x: 400, y: 120 }]
    const breaches = breachesOf(geometry, placement, new Map([[0, through]]), text)
    expect(breaches.map((one) => one.rule)).toContain('crosses-an-element')
    expect(countByTier(breaches).hard).toBeGreaterThan(0)
  })

  it('reports a jog as soft', () => {
    const jogging: Point[] = [
      { x: 80, y: 120 }, { x: 150, y: 120 }, { x: 150, y: 60 }, { x: 160, y: 60 }, { x: 160, y: 30 },
      { x: 300, y: 30 }, { x: 300, y: 120 }, { x: 400, y: 120 },
    ]
    const breaches = breachesOf(geometry, placement, new Map([[0, jogging]]), text)
    expect(breaches.filter((one) => one.rule === 'jog').every((one) => one.tier === 'soft')).toBe(true)
    expect(countByTier(breaches).soft).toBeGreaterThan(0)
  })

  it('reports a relation the router could not reach as unroutable', () => {
    const breaches = breachesOf(geometry, placement, new Map(), text, new Set([0]))
    expect(breaches.map((one) => one.rule)).toEqual(['unroutable'])
  })

  it('finds nothing hard on the route the router itself chose', () => {
    const routed = fullPass(geometry, placement)
    const courses = new Map([...routed.routes].map(([key, one]) => [Number(key), one.course]))
    const breaches = breachesOf(geometry, placement, courses, text, new Set(routed.unroutable.map(Number)))
    expect(countByTier(breaches).hard).toBe(0)
  })
})
