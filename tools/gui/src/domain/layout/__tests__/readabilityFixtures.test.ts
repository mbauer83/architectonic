/**
 * The readability rules of a route, held to the cases the Python domain is held to.
 *
 * `tests/fixtures/layout_geometry/readability.json` states the rules' tiers as data, the constants
 * they are stated in, and cases with the Python domain's answers. A rule moved between tiers, a
 * constant changed, or a predicate answered differently on one side fails here or in pytest.
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import type { Extent, Point } from '../geometry'
import {
  END_RUN,
  LINE_CLEARANCE,
  RULE_TIERS,
  SHORTEST_SEGMENT,
  TEXT_PADDING,
  BAND_MARGIN,
  bendsAtEnds,
  kinks,
  runsAlong,
  squareCourse,
  textsCrossed,
} from '../routeQuality'

type XY = readonly [number, number]

interface Readability {
  tiers: Record<string, string>
  constants: Record<string, number>
  text: { name: string; course: XY[]; regions: Record<string, Extent>; crossed: string[] }[]
  bends_at_ends: { name: string; course: XY[]; decorated: [boolean, boolean]; breaches: string[] }[]
  kinks: { name: string; course: XY[]; segments: number[] }[]
  runs_along: { name: string; course: XY[]; others: XY[][]; borders: Extent[]; segments: number[] }[]
  square: { name: string; through: XY[]; course: XY[] }[]
}

const readability = JSON.parse(
  readFileSync(
    fileURLToPath(new URL('../../../../../../tests/fixtures/layout_geometry/readability.json', import.meta.url)),
    'utf-8',
  ),
) as Readability

const points = (pairs: readonly XY[]): Point[] => pairs.map(([x, y]) => ({ x, y }))

describe('the rules and their tiers', () => {
  it('sorts every rule into the tier the Python domain does', () => {
    expect(RULE_TIERS).toEqual(readability.tiers)
  })

  it('states each rule in the same constants', () => {
    expect({ END_RUN, SHORTEST_SEGMENT, LINE_CLEARANCE, TEXT_PADDING, BAND_MARGIN }).toEqual(readability.constants)
  })
})

describe('a line never passes through text', () => {
  it.each(readability.text)('$name', ({ course, regions, crossed }) => {
    expect(textsCrossed(points(course), new Map(Object.entries(regions)))).toEqual(crossed)
  })
})

describe('A: no bend at or right behind an end', () => {
  it.each(readability.bends_at_ends)('$name', ({ course, decorated, breaches }) => {
    expect(bendsAtEnds(points(course), decorated)).toEqual(breaches)
  })
})

describe('B: a jog, avoided at a cost', () => {
  it.each(readability.kinks)('$name', ({ course, segments }) => {
    expect(kinks(points(course))).toEqual(segments)
  })
})

describe('C: no run along another line or a border', () => {
  it.each(readability.runs_along)('$name', ({ course, others, borders, segments }) => {
    expect(runsAlong(points(course), others.map(points), borders)).toEqual(segments)
  })
})

describe('the square course of a drawn line', () => {
  it.each(readability.square)('$name', ({ through, course }) => {
    expect(squareCourse(points(through)).map(({ x, y }) => [x, y])).toEqual(course)
  })
})
