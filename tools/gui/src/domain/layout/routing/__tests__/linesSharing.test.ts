/**
 * `Lines` answers how many spans run along a run from cells of line and stretch, not by comparing the
 * run with every span on every line near it. What it answers must be what that comparison answers:
 * a span sharing more than one unit of the run's stretch, on a line in range, counted once, however
 * many cells the span or the run passes through, on either side of zero.
 */
import { describe, expect, it } from 'vitest'
import type { Point } from '../../geometry'
import { Lines } from '../lines'

/** A small deterministic generator, so a failure names the same spans every run. */
const numbers = (seed: number) => {
  let state = seed
  return (below: number): number => {
    state = (state * 1103515245 + 12345) % 2147483648
    return state % below
  }
}

type Span = readonly [level: boolean, at: number, low: number, high: number]

/** Every span compared with the run: the rule the cells must answer by. */
const scanned = (spans: readonly Span[], a: Point, b: Point, least: number, most: number): number => {
  const level = a.y === b.y
  const [low, high] = level ? [Math.min(a.x, b.x), Math.max(a.x, b.x)] : [Math.min(a.y, b.y), Math.max(a.y, b.y)]
  return spans.filter(([isLevel, at, spanLow, spanHigh]) =>
    isLevel === level && least <= at && at <= most && Math.min(high, spanHigh) - Math.max(low, spanLow) > 1).length
}

const pointsOf = ([level, at, low, high]: Span): [Point, Point] =>
  level ? [{ x: low, y: at }, { x: high, y: at }] : [{ x: at, y: low }, { x: at, y: high }]

describe('how many spans run along a run', () => {
  const next = numbers(7)
  const place = () => next(3000) - 1500
  const spans: Span[] = Array.from({ length: 400 }, (_, index) => {
    const low = place()
    // Short spans and spans across many cells alike, some touching the run's ends exactly.
    const length = index % 5 === 0 ? 1 + next(2500) : 1 + next(120)
    return [index % 2 === 0, Math.round(place() / 4) * 4, low, low + length] as const
  })
  // The same span twice is two spans.
  spans.push(spans[0], spans[1])
  const lines = new Lines()
  for (const span of spans) lines.add(...pointsOf(span))

  it('counts what comparing every span counts, near a run and between two lines', () => {
    for (let trial = 0; trial < 600; trial += 1) {
      const [level, at, low] = [trial % 2 === 0, Math.round(place() / 4) * 4, place()]
      const run: Span = [level, at, low, low + (trial % 7 === 0 ? next(3000) : next(200))]
      const [a, b] = pointsOf(run)
      const within = [6, 12, 60][trial % 3]
      expect(lines.near(a, b, within)).toBe(scanned(spans, a, b, at - within + 1e-9, at + within - 1e-9))
      const [least, most] = [at - next(90), at + next(90)]
      expect(lines.between(b, a, least, most)).toBe(scanned(spans, a, b, least, most))
    }
  })

  it('counts a span that shares exactly one unit as not running along', () => {
    const one = new Lines()
    one.add({ x: 0, y: 10 }, { x: 300, y: 10 })
    expect(one.near({ x: 299, y: 10 }, { x: 600, y: 10 }, 6)).toBe(0)
    expect(one.near({ x: 298, y: 10 }, { x: 600, y: 10 }, 6)).toBe(1)
    expect(one.along({ x: -600, y: 14 }, { x: 600, y: 14 })).toBe(true)
  })
})
