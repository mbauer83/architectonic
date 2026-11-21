/**
 * What makes a route readable, beyond staying attached — the rules a router keeps and a picture is
 * checked for, in two tiers.
 *
 * The TypeScript mirror of `src/domain/diagrams/layout/route_quality.py` and `text_clearance.py`,
 * held equal to them by `tests/fixtures/layout_geometry/readability.json`, which states the tiers as
 * data along with the cases. Hard rules a route never breaks: no line through text, no bend at or
 * right behind an end's decoration, no run along another line or a border. Soft ones it avoids at a
 * cost: a jog, two decorations together, a label obscured.
 */
import type { Extent, Point } from './geometry'
import { distanceBetween, isEnteredBy, shrunkBy } from './geometry'

export type Tier = 'hard' | 'soft'

/** Every readability rule by name, and its tier: the one statement of which rules a route may give up. */
export const RULE_TIERS: Readonly<Record<string, Tier>> = {
  text: 'hard',
  'bend-at-an-end': 'hard',
  'runs-along': 'hard',
  'leaves-common-box': 'hard',
  jog: 'soft',
  'heads-together': 'soft',
  'label-obscured': 'soft',
}

/** How long a route runs straight into an end where it bends at all: a decoration and a clear run. */
export const END_RUN = 30

/** The shortest segment between two bends. */
export const SHORTEST_SEGMENT = 16

/** How close two parallel runs may come, or a run and a border, before they read as one line. */
export const LINE_CLEARANCE = 6

/** The room kept round text, which a line keeps out of too. */
export const TEXT_PADDING = 3

const THROUGH_TEXT_MARGIN = 1
const SHARED_LENGTH = 1
const SQUARE = 0.5

export type BendAtAnEnd = 'A:source' | 'A:target'

const segments = (course: readonly Point[]): (readonly [Point, Point])[] =>
  course.slice(1).map((point, index) => [course[index], point] as const)

/** Whether any segment of *course* runs into *region*, more than a graze. */
export const runsThroughText = (course: readonly Point[], region: Extent): boolean => {
  const interior = shrunkBy(region, THROUGH_TEXT_MARGIN)
  return interior !== null && segments(course).some(([start, end]) => isEnteredBy(interior, start, end))
}

/** The text regions, by key, that *course* runs through. */
export const textsCrossed = (course: readonly Point[], regions: ReadonlyMap<string, Extent>): string[] =>
  [...regions].filter(([, region]) => runsThroughText(course, region)).map(([key]) => key)

/** A: the decorated ends of *course* whose straight run is shorter than END_RUN, where it bends at all. */
export const bendsAtEnds = (
  course: readonly Point[],
  decorated: readonly [boolean, boolean] = [true, true],
): BendAtAnEnd[] => {
  if (course.length <= 2) return []
  const ends: readonly (readonly [BendAtAnEnd, number, boolean])[] = [
    ['A:source', distanceBetween(course[0], course[1]), decorated[0]],
    ['A:target', distanceBetween(course[course.length - 1], course[course.length - 2]), decorated[1]],
  ]
  return ends.filter(([, run, marked]) => marked && run < END_RUN - SQUARE).map(([breach]) => breach)
}

/** The index of each run that turns back along its axis a second time or more. */
const weaving = (course: readonly Point[]): Set<number> => {
  const found = new Set<number>()
  for (const level of [true, false]) {
    let heading = 0
    let turned = 0
    segments(course).forEach(([a, b], index) => {
      const step = level ? b.x - a.x : b.y - a.y
      if (Math.abs(step) <= SQUARE) return
      const way = step > 0 ? 1 : -1
      if (heading !== 0 && way !== heading) {
        turned += 1
        if (turned >= 2) found.add(index)
      }
      heading = way
    })
  }
  return found
}

/**
 * B: the index of each segment between two bends shorter than SHORTEST_SEGMENT, and of each run that
 * turns back along its axis a second time — a route going round something turns back once; one that
 * weaves turns back twice.
 */
export const kinks = (course: readonly Point[]): number[] => {
  const found = weaving(course)
  segments(course).forEach(([start, end], index) => {
    if (index >= 1 && index <= course.length - 3 && distanceBetween(start, end) < SHORTEST_SEGMENT) found.add(index)
  })
  return [...found].sort((one, other) => one - other)
}

interface Span {
  readonly level: boolean
  readonly at: number
  readonly low: number
  readonly high: number
}

const spanOf = (start: Point, end: Point): Span | null => {
  if (Math.abs(start.y - end.y) <= SQUARE && Math.abs(start.x - end.x) > SQUARE) {
    return { level: true, at: start.y, low: Math.min(start.x, end.x), high: Math.max(start.x, end.x) }
  }
  if (Math.abs(start.x - end.x) <= SQUARE && Math.abs(start.y - end.y) > SQUARE) {
    return { level: false, at: start.x, low: Math.min(start.y, end.y), high: Math.max(start.y, end.y) }
  }
  return null
}

const edgesOf = (extent: Extent): Span[] => [
  { level: true, at: extent.top, low: extent.left, high: extent.right },
  { level: true, at: extent.bottom, low: extent.left, high: extent.right },
  { level: false, at: extent.left, low: extent.top, high: extent.bottom },
  { level: false, at: extent.right, low: extent.top, high: extent.bottom },
]

const alongside = (run: Span, other: Span): boolean =>
  run.level === other.level &&
  Math.abs(run.at - other.at) < LINE_CLEARANCE &&
  Math.min(run.high, other.high) - Math.max(run.low, other.low) > SHARED_LENGTH

/** C: the index of each segment of *course* running along another course's segment, or a border. */
export const runsAlong = (
  course: readonly Point[],
  others: readonly (readonly Point[])[] = [],
  borders: readonly Extent[] = [],
): number[] => {
  const lines = [
    ...others.flatMap((other) => segments(other).flatMap(([start, end]) => spanOf(start, end) ?? [])),
    ...borders.flatMap(edgesOf),
  ]
  return segments(course)
    .map(([start, end], index) => ({ index, run: spanOf(start, end) }))
    .filter(({ run }) => run !== null && lines.some((line) => alongside(run, line)))
    .map(({ index }) => index)
}

/** The orthogonal course a drawn line with rounded bends follows: each rounding taken back to its corner. */
export const squareCourse = (through: readonly Point[]): Point[] => {
  if (through.length <= 2) return [...through]
  const corners: Point[] = [through[0]]
  for (let index = 1; index < through.length - 1; index += 1) {
    const before = through[index - 1]
    const here = through[index]
    const after = through[index + 1]
    const into = spanOf(before, here)
    const outOf = spanOf(here, after)
    if (into !== null && outOf === null) {
      corners.push(Math.abs(before.x - here.x) <= SQUARE ? { x: here.x, y: after.y } : { x: after.x, y: here.y })
    } else if (into !== null && outOf !== null) {
      corners.push(here)
    }
  }
  corners.push(through[through.length - 1])
  return corners
}
