/**
 * The course a stated route runs: from its port, through its bends, to its port, every segment
 * upright or level.
 *
 * The TypeScript mirror of `src/domain/diagrams/layout/orthogonal.py`. The two are one specification
 * implemented twice — the server draws and routes, the canvas shows a route following an element
 * while it is dragged — and are held equal by the cases in `tests/fixtures/layout_geometry/`, which
 * both are tested against. Change the rule in both, then rewrite the fixtures from the Python side.
 *
 * A route is spelled as the layout block of a diagram's frontmatter spells one: `from` and `to` are
 * a side and a fraction along it, `via` the bends, `label` where its label is anchored.
 */
import type { Extent, Point } from './geometry'
import { courseLength, distanceBetween, heightOf, widthOf } from './geometry'

export type Side = 'top' | 'right' | 'bottom' | 'left'

/** Where a relation attaches: a side of its element, and how far along it from the top or left. */
export interface Port {
  readonly side: Side
  readonly at: number
}

/** Where a relation's label sits: a fraction along its route, and an offset from that point. */
export interface LabelAnchor {
  readonly at: number
  readonly dx: number
  readonly dy: number
}

export type Bend = readonly [number, number]

/** How one drawn relation runs. Anything left unstated is the router's to decide. */
export interface Route {
  readonly from?: Port
  readonly to?: Port
  readonly via?: readonly Bend[]
  readonly label?: LabelAnchor
}

/** How far a relation runs straight out of its element before it may turn: the router's margin. */
export const STUB = 12

/** How far two points may sit off one line and still count as on it. */
export const IN_LINE = 0.5

/** Which way each side faces. */
export const OUTWARD: Readonly<Record<Side, readonly [number, number]>> = {
  top: [0, -1],
  right: [1, 0],
  bottom: [0, 1],
  left: [-1, 0],
}

/** *value* to the nearest whole number, a half going up — the one rounding both languages share. */
export const halfUp = (value: number): number => Math.floor(value + 0.5)

/** Whether a relation attached on *side* leaves it horizontally. */
export const leavesLevel = (side: Side): boolean => side === 'left' || side === 'right'

/** Where *port* lies on *extent*'s border: along a side from its top or its left. */
export const portPoint = (extent: Extent, port: Port): Point => {
  const alongX = extent.left + port.at * widthOf(extent)
  const alongY = extent.top + port.at * heightOf(extent)
  const places: Record<Side, Point> = {
    top: { x: alongX, y: extent.top },
    bottom: { x: alongX, y: extent.bottom },
    left: { x: extent.left, y: alongY },
    right: { x: extent.right, y: alongY },
  }
  return places[port.side]
}

const last = (course: readonly Point[]): Point => course[course.length - 1]

/** The course from *start* through each bend, an elbow added wherever two do not line up. */
const throughBends = (
  start: Point,
  bends: readonly Point[],
  leavesLevelFirst: boolean,
): { course: Point[]; level: boolean } => {
  const course = [start]
  let level = leavesLevelFirst
  for (const bend of bends) {
    const before = last(course)
    if (Math.abs(bend.x - before.x) > IN_LINE && Math.abs(bend.y - before.y) > IN_LINE) {
      course.push(level ? { x: bend.x, y: before.y } : { x: before.x, y: bend.y })
    }
    level = Math.abs(bend.y - last(course).y) <= IN_LINE
    course.push(bend)
  }
  return { course, level }
}

/**
 * *course* carried on to *end*, arriving in the direction its side needs: travelling as it must
 * arrive and not in line, a Z through the midpoint; travelling the other way, an L; in line, straight.
 */
const joinedTo = (course: readonly Point[], level: boolean, end: Point, arrivesLevel: boolean): Point[] => {
  const before = last(course)
  const inLine = arrivesLevel
    ? Math.abs(before.y - end.y) <= IN_LINE
    : Math.abs(before.x - end.x) <= IN_LINE
  if (inLine) return [...course, end]
  if (level !== arrivesLevel) {
    return [...course, arrivesLevel ? { x: before.x, y: end.y } : { x: end.x, y: before.y }, end]
  }
  if (arrivesLevel) {
    const middle = (before.x + end.x) / 2
    return [...course, { x: middle, y: before.y }, { x: middle, y: end.y }, end]
  }
  const middle = (before.y + end.y) / 2
  return [...course, { x: before.x, y: middle }, { x: end.x, y: middle }, end]
}

/**
 * *course* without the points that turn nothing: a repeat, or one passed in the middle of a straight
 * run. A point the course turns back at is kept: a spur is part of what was stated.
 */
const withoutIdlePoints = (course: readonly Point[]): Point[] => {
  if (course.length <= 2) return [...course]
  const kept = [course[0]]
  for (let index = 1; index < course.length - 1; index += 1) {
    const before = last(kept)
    const here = course[index]
    const after = course[index + 1]
    const repeats = Math.abs(before.x - here.x) < IN_LINE && Math.abs(before.y - here.y) < IN_LINE
    const upright = Math.abs(before.x - here.x) < IN_LINE && Math.abs(here.x - after.x) < IN_LINE
    const level = Math.abs(before.y - here.y) < IN_LINE && Math.abs(here.y - after.y) < IN_LINE
    const passedUpright = upright && (here.y - before.y) * (after.y - here.y) >= 0
    const passedLevel = level && (here.x - before.x) * (after.x - here.x) >= 0
    if (!(repeats || passedUpright || passedLevel)) kept.push(here)
  }
  return [...kept, last(course)]
}

/** The orthogonal course from *start* through *bends* to *end*, leaving and arriving by its sides. */
export const completedCourse = (
  start: Point,
  sourceSide: Side,
  bends: readonly Point[],
  end: Point,
  targetSide: Side,
): Point[] => {
  const { course, level } = throughBends(start, bends, leavesLevel(sourceSide))
  return withoutIdlePoints(joinedTo(course, level, end, leavesLevel(targetSide)))
}

export const bendsOf = (route: Route): Point[] => (route.via ?? []).map(([x, y]) => ({ x, y }))

/**
 * Where *route* runs as far as it says: completed between two stated ends, else from the one it
 * states. An end whose port is unstated, or whose element's extent is not known, is the router's:
 * the course stops at the last bend before it. The answer may be a single point, or nothing.
 */
export const statedCourse = (route: Route, source: Extent | null, target: Extent | null): Point[] => {
  const bends = bendsOf(route)
  const start = source && route.from ? { point: portPoint(source, route.from), side: route.from.side } : null
  const end = target && route.to ? { point: portPoint(target, route.to), side: route.to.side } : null
  if (start && end) return completedCourse(start.point, start.side, bends, end.point, end.side)
  if (start) return withoutIdlePoints(throughBends(start.point, bends, leavesLevel(start.side)).course)
  if (end) {
    const backwards = throughBends(end.point, [...bends].reverse(), leavesLevel(end.side)).course
    return withoutIdlePoints(backwards).reverse()
  }
  return bends
}

/** Where *route* runs between two elements, or null where it leaves a port for the router to decide. */
export const courseOf = (route: Route, source: Extent, target: Extent): Point[] | null =>
  route.from && route.to ? statedCourse(route, source, target) : null

/** The point a fraction *at* of the way along *course*. */
export const pointAlong = (course: readonly Point[], at: number): Point => {
  const goal = at * courseLength(course)
  let walked = 0
  for (let index = 0; index < course.length - 1; index += 1) {
    const start = course[index]
    const end = course[index + 1]
    const length = distanceBetween(start, end)
    if (length > 0 && walked + length >= goal) {
      const share = (goal - walked) / length
      return { x: start.x + share * (end.x - start.x), y: start.y + share * (end.y - start.y) }
    }
    walked += length
  }
  return last(course)
}

/** How far along *course*, from 0 to 1, the place nearest *point* lies. */
export const fractionAlong = (course: readonly Point[], point: Point): number => {
  let nearest = Number.POSITIVE_INFINITY
  let reached = 0
  let walked = 0
  for (let index = 0; index < course.length - 1; index += 1) {
    const start = course[index]
    const end = course[index + 1]
    const length = distanceBetween(start, end)
    if (length === 0) continue
    const along =
      ((point.x - start.x) * (end.x - start.x) + (point.y - start.y) * (end.y - start.y)) / length ** 2
    const share = Math.max(0, Math.min(1, along))
    const foot = { x: start.x + share * (end.x - start.x), y: start.y + share * (end.y - start.y) }
    const distance = distanceBetween(foot, point)
    if (distance < nearest) {
      nearest = distance
      reached = walked + share * length
    }
    walked += length
  }
  return walked > 0 ? reached / walked : 0
}
