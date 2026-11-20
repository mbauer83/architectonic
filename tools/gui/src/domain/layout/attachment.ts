/**
 * Arrows stay attached: what a route owes the two elements it joins, and how it is kept when one
 * moves.
 *
 * The TypeScript mirror of `src/domain/diagrams/layout/attachment.py`, held equal to it by the cases
 * in `tests/fixtures/layout_geometry/`. Five invariants:
 *
 * - **I1** each end leaves its element straight outward by at least one stub;
 * - **I2** no segment passes through the relation's own ends;
 * - **I3** when an element moves or is resized, the bend next to each attached end follows the port
 *   on the axis that keeps that end's segment straight — the arrow keeps its shape;
 * - **I4** only where following breaks I1 or I2: the end turns to the side its route lies beyond,
 *   failing that the bend next to it goes, failing that the arrow is formed afresh facing its ends;
 * - **I5** an arrow crosses no other element. Finding out is decided here; going around is the
 *   server's router's work, so `keepAttached` names the arrows that need it. The canvas shows the
 *   followed shape while something is dragged and takes the server's route when it is dropped.
 *
 * Two connected elements that overlap or touch are a conflict no route satisfies: reported, never
 * repaired.
 */
import type { Extent, Point } from './geometry'
import { centreOf, encloses, heightOf, isEnteredBy, shrunkBy, widthOf } from './geometry'
import type { Port, Route, Side } from './orthogonal'
import {
  IN_LINE,
  OUTWARD,
  STUB,
  courseOf,
  halfUp,
  leavesLevel,
  portPoint,
  statedCourse,
} from './orthogonal'

/** How far inside an element a segment must run before it counts as through it. */
export const THROUGH_MARGIN = 2

/** How close to a corner a turned end may attach, as a fraction of the side. */
const FROM_THE_CORNER = 0.1

/** How many times an end is turned or relieved of a bend before the arrow is formed afresh. */
const TRIES_PER_END = 3

const SIDES_IN_ORDER: readonly Side[] = ['top', 'right', 'bottom', 'left']

/** What a route fails to keep towards its own two ends. */
export type Breach = 'I1:source' | 'I1:target' | 'I2:source' | 'I2:target'

/** *value* as a port's fraction is written: within the side, to four places. */
export const fraction = (value: number): number =>
  halfUp(Math.max(0, Math.min(1, value)) * 10000) / 10000

/** Whether the run from *start* goes along the side's outward normal for at least one stub. */
export const leavesOutward = (side: Side, start: Point, toward: Point): boolean => {
  const [outX, outY] = OUTWARD[side]
  const travelled = (toward.x - start.x) * outX + (toward.y - start.y) * outY
  const strayed = Math.abs((toward.x - start.x) * outY) + Math.abs((toward.y - start.y) * outX)
  return travelled >= STUB && strayed <= IN_LINE
}

/** Whether any segment of *course* passes inside *extent*, a margin in from its border. */
export const runsThrough = (course: readonly Point[], extent: Extent): boolean => {
  const interior = shrunkBy(extent, THROUGH_MARGIN)
  return (
    interior !== null &&
    course.slice(1).some((point, index) => isEnteredBy(interior, course[index], point))
  )
}

/**
 * Everything *route* fails to keep towards its ends (I1, I2), as far as it and the extents say. An
 * end with no stated port is not judged for how it leaves; an element of unknown extent not at all.
 */
export const breachesOf = (route: Route, source: Extent | null, target: Extent | null): Breach[] => {
  const course = statedCourse(route, source, target)
  if (course.length < 2) return []
  const checks: readonly (readonly [Breach, boolean])[] = [
    ['I1:source', !!route.from && !!source && !leavesOutward(route.from.side, course[0], course[1])],
    [
      'I1:target',
      !!route.to &&
        !!target &&
        !leavesOutward(route.to.side, course[course.length - 1], course[course.length - 2]),
    ],
    ['I2:source', !!source && runsThrough(course, source)],
    ['I2:target', !!target && runsThrough(course, target)],
  ]
  return checks.filter(([, broken]) => broken).map(([breach]) => breach)
}

/** Whether two connected elements overlap or sit closer than a stub: a conflict no route satisfies. */
export const endsConflict = (source: Extent, target: Extent): boolean =>
  source.left < target.right + STUB &&
  target.left < source.right + STUB &&
  source.top < target.bottom + STUB &&
  target.top < source.bottom + STUB

/**
 * The elements other than its own ends that *course* passes through (I5). An element one of the
 * ends is drawn inside is not another element to it.
 */
export const elementsCrossed = (
  course: readonly Point[],
  extents: ReadonlyMap<string, Extent>,
  ownEnds: readonly [string, string],
): string[] => {
  const own = ownEnds.flatMap((end) => {
    const extent = extents.get(end)
    return extent ? [extent] : []
  })
  return [...extents]
    .filter(
      ([key, extent]) =>
        !ownEnds.includes(key) &&
        !own.some((end) => encloses(extent, end)) &&
        runsThrough(course, extent),
    )
    .map(([key]) => key)
}

const flipped = (route: Route): Route => ({
  ...route,
  from: route.to,
  to: route.from,
  via: [...(route.via ?? [])].reverse(),
})

/** The point the route makes for on leaving its source: its first bend, else its other end. */
const nextAfterSource = (route: Route, target: Extent): Point => {
  const [first] = route.via ?? []
  if (first) return { x: first[0], y: first[1] }
  return route.to ? portPoint(target, route.to) : centreOf(target)
}

/** I3: the first bend moved onto the source port's line, on the axis that keeps that run straight. */
const firstBendFollowing = (route: Route, source: Extent): Route => {
  const [first, ...rest] = route.via ?? []
  if (!first || !route.from) return route
  const port = portPoint(source, route.from)
  const followed: readonly [number, number] = leavesLevel(route.from.side)
    ? [first[0], halfUp(port.y)]
    : [halfUp(port.x), first[1]]
  return { ...route, via: [followed, ...rest] }
}

const outwardRun = (route: Route, source: Extent, target: Extent): number => {
  if (!route.from) return STUB
  const start = portPoint(source, route.from)
  const toward = nextAfterSource(route, target)
  const [outX, outY] = OUTWARD[route.from.side]
  return (toward.x - start.x) * outX + (toward.y - start.y) * outY
}

/** How far along a side *coordinate* lies: down a left or right side, across a top or bottom one. */
const share = (extent: Extent, coordinate: number, level: boolean): number => {
  const length = level ? heightOf(extent) : widthOf(extent)
  return length > 0 ? (coordinate - (level ? extent.top : extent.left)) / length : 0.5
}

/** I4: the side of *source* its route lies beyond by at least a stub, or null where it lies beyond none. */
const sideFacing = (route: Route, source: Extent, target: Extent): Port | null => {
  const toward = nextAfterSource(route, target)
  const clear: Record<Side, number> = {
    top: source.top - toward.y,
    right: toward.x - source.right,
    bottom: toward.y - source.bottom,
    left: source.left - toward.x,
  }
  // The first of equally clear sides, in the order both implementations walk them.
  const side = SIDES_IN_ORDER.reduce((best, candidate) => (clear[candidate] > clear[best] ? candidate : best))
  if (clear[side] < STUB) return null
  const level = leavesLevel(side)
  const along = share(source, level ? toward.y : toward.x, level)
  return { side, at: fraction(Math.max(FROM_THE_CORNER, Math.min(1 - FROM_THE_CORNER, along))) }
}

/** The route with its source end following (I3) and, where that is not enough, turned or relieved (I4). */
const settledAtSource = (route: Route, source: Extent, target: Extent): Route => {
  let settled = firstBendFollowing(route, source)
  for (let attempt = 0; attempt < TRIES_PER_END; attempt += 1) {
    if (outwardRun(settled, source, target) >= STUB) break
    const turned = sideFacing(settled, source, target)
    if (turned) {
      settled = firstBendFollowing({ ...settled, from: turned }, source)
    } else if (settled.via?.length) {
      settled = firstBendFollowing({ ...settled, via: settled.via.slice(1) }, source)
    } else {
      break
    }
  }
  return settled
}

/** The ways to join two elements afresh, the most direct first: straight, a Z, an L either way round. */
const candidatesFacing = (source: Extent, target: Extent): Route[] => {
  const gapX = Math.max(target.left - source.right, source.left - target.right)
  const gapY = Math.max(target.top - source.bottom, source.top - target.bottom)
  const rightward = centreOf(target).x > centreOf(source).x
  const downward = centreOf(target).y > centreOf(source).y
  const across: readonly [Side, Side] = rightward ? ['right', 'left'] : ['left', 'right']
  const down: readonly [Side, Side] = downward ? ['bottom', 'top'] : ['top', 'bottom']
  const level = gapX >= gapY
  const facing = level ? across : down
  const shared: readonly [number, number] = level
    ? [Math.max(source.top, target.top), Math.min(source.bottom, target.bottom)]
    : [Math.max(source.left, target.left), Math.min(source.right, target.right)]
  const straight: Route[] = []
  if (shared[1] > shared[0]) {
    const middle = (shared[0] + shared[1]) / 2
    straight.push({
      from: { side: facing[0], at: fraction(share(source, middle, level)) },
      to: { side: facing[1], at: fraction(share(target, middle, level)) },
    })
  }
  return [
    ...straight,
    { from: { side: facing[0], at: 0.5 }, to: { side: facing[1], at: 0.5 } },
    { from: { side: across[0], at: 0.5 }, to: { side: down[1], at: 0.5 } },
    { from: { side: down[0], at: 0.5 }, to: { side: across[1], at: 0.5 } },
  ]
}

/** A route facing its two ends, keeping only where *route*'s label sits: the first way that breaks nothing. */
export const formedAfresh = (route: Route, source: Extent, target: Extent): Route => {
  const candidates = candidatesFacing(source, target)
  const chosen = candidates.find((made) => breachesOf(made, source, target).length === 0) ?? candidates[0]
  return route.label ? { ...chosen, label: route.label } : chosen
}

/** *route* as it runs once its ends are where *source* and *target* now are (I3, then I4). */
export const reattached = (route: Route, source: Extent, target: Extent): Route => {
  if (!route.from || !route.to) return route
  const fromSource = settledAtSource(route, source, target)
  const settled = flipped(settledAtSource(flipped(fromSource), target, source))
  return breachesOf(settled, source, target).length > 0 ? formedAfresh(route, source, target) : settled
}

/** What keeping arrows attached came to, for one change to where elements are. */
export interface Reattachment {
  /** Every route, by relation key: those of the elements that changed repaired, the rest as they were. */
  readonly routes: ReadonlyMap<string, Route>
  /** I5 — each repaired relation that now crosses another element, with the elements it crosses. */
  readonly crossing: ReadonlyMap<string, readonly string[]>
  /** Relations whose two elements overlap or touch, which no route joins. */
  readonly conflicts: readonly string[]
}

/** Where everything is after a change, and which elements the change moved or resized. */
export interface ChangedArrangement {
  /** The two elements each relation joins, by relation key. */
  readonly ends: ReadonlyMap<string, readonly [string, string]>
  /** Where every element sits now. */
  readonly extents: ReadonlyMap<string, Extent>
  readonly changed: readonly string[]
}

/**
 * Every route kept attached after the elements in *changed* moved or were resized. Only relations
 * with an end among them are touched; one whose route leaves a port unstated, that joins an element
 * to itself, or one of whose ends has no known extent is left as it is.
 */
export const keepAttached = (
  routes: ReadonlyMap<string, Route>,
  { ends, extents, changed }: ChangedArrangement,
): Reattachment => {
  const kept = new Map(routes)
  const crossing = new Map<string, readonly string[]>()
  const conflicts: string[] = []
  for (const [key, route] of routes) {
    const joined = ends.get(key)
    if (!joined || joined[0] === joined[1] || !joined.some((end) => changed.includes(end))) continue
    const source = extents.get(joined[0])
    const target = extents.get(joined[1])
    if (!source || !target || !route.from || !route.to) continue
    if (endsConflict(source, target)) conflicts.push(key)
    const repaired = reattached(route, source, target)
    kept.set(key, repaired)
    const course = courseOf(repaired, source, target)
    const crossed = course ? elementsCrossed(course, extents, joined) : []
    if (crossed.length > 0) crossing.set(key, crossed)
  }
  return { routes: kept, crossing, conflicts }
}
