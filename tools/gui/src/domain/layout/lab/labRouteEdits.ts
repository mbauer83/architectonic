/**
 * Shaping a line by hand (sketch 02·3–02·5): moving an end along its element's outline or onto another
 * side, moving a segment sideways, adding, moving and removing bends, straightening, and anchoring the
 * label. Each answer is the line's stated route, spelled as the layout block spells one (`Route`).
 *
 * What a route states is the user's and the router keeps it. A line whose bends are stated runs them;
 * one that states only ports is routed between them (`labRouting`). So a bend or a segment edit states
 * the whole route — both ports and every corner — and moving an end onto another side, or
 * straightening, drops the bends and leaves the way round to the router, which keeps the hard rules.
 *
 * The run out of each port is kept (`runFor`): never shorter than a stub, nor than a decoration's run
 * at a decorated end, so no edit puts a bend at or behind an arrowhead.
 */
import type { Extent, Point } from '../geometry'
import { distanceBetween, heightOf, widthOf } from '../geometry'
import { fraction } from '../attachment'
import type { Bend, LabelAnchor, Port, Route, Side } from '../orthogonal'
import { IN_LINE, OUTWARD, fractionAlong, halfUp, leavesLevel, pointAlong, portPoint } from '../orthogonal'
import { runFor } from '../routing/scene'
import type { RoutedConnector } from '../routing/scene'
import type { Arrangement } from './labArrangement'

/** Which end of a line: its source (`from`) or its target (`to`), as a route names them. */
export type End = 'from' | 'to'

/** How far from a corner an end may be slid, in pixels. */
const CORNER_CLEARANCE = 4

const bend = (point: Point): Bend => [halfUp(point.x), halfUp(point.y)]
const pointOf = ([x, y]: Bend): Point => ({ x, y })

/** *routed* as a whole stated route, the anchor of *stated* kept: its ports and every corner a bend. */
export const statedWhole = (routed: RoutedConnector, stated?: Route): Route => ({
  ...(stated?.label ? { label: stated.label } : {}),
  from: routed.sourcePort,
  to: routed.targetPort,
  via: routed.course.slice(1, -1).map(bend),
})

/**
 * The bends a selected line shows as handles: the stated ones where its route states them, else the
 * corners of the course the router gave it.
 */
export const bendsShown = (course: readonly Point[], stated?: Route): Point[] =>
  stated?.via?.length ? stated.via.map(pointOf) : course.slice(1, -1)

/**
 * The port on *extent* nearest *point*: the side closest to it, and how far along, kept clear of the
 * corners. Within *snap* of *inLineWith* along that side, it lines up with it, so the line can run
 * straight to the other end.
 */
export const portNear = (extent: Extent, point: Point, inLineWith: Point | null = null, snap = 0): Port => {
  const across = (low: number, high: number, value: number) => Math.max(low - value, 0, value - high)
  const [offX, offY] = [across(extent.left, extent.right, point.x), across(extent.top, extent.bottom, point.y)]
  const distances: Readonly<Record<Side, number>> = {
    left: Math.hypot(point.x - extent.left, offY), right: Math.hypot(point.x - extent.right, offY),
    top: Math.hypot(point.y - extent.top, offX), bottom: Math.hypot(point.y - extent.bottom, offX),
  }
  const side = (Object.keys(distances) as Side[])
    .reduce((one, other) => (distances[one] <= distances[other] ? one : other))
  const level = leavesLevel(side)
  const [low, length] = level ? [extent.top, heightOf(extent)] : [extent.left, widthOf(extent)]
  const wanted = level ? point.y : point.x
  const lined = inLineWith === null ? null : level ? inLineWith.y : inLineWith.x
  const along = lined !== null && Math.abs(lined - wanted) <= snap ? lined : wanted
  const kept = Math.min(low + length - CORNER_CLEARANCE, Math.max(low + CORNER_CLEARANCE, along))
  return { side, at: length > 0 ? fraction((kept - low) / length) : 0.5 }
}

/**
 * *route* with its *end* at *port* on *extent*. Along the same side the bends keep their shape, the one
 * next to the end following it so the end's run stays straight (I3). Onto another side the bends go:
 * the line leaves by its new side and the router takes it round.
 */
export const withEndAt = (route: Route, end: End, port: Port, extent: Extent): Route => {
  const sameSide = route[end]?.side === port.side
  if (!route.via?.length || !sameSide) {
    const { via: _dropped, ...rest } = route
    return { ...rest, [end]: port }
  }
  const at = portPoint(extent, port)
  const via = [...route.via]
  const index = end === 'from' ? 0 : via.length - 1
  const [x, y] = via[index]
  via[index] = leavesLevel(port.side) ? [x, halfUp(at.y)] : [halfUp(at.x), y]
  return { ...route, [end]: port, via }
}

/** *route* without its bends, ports and label kept: the router takes it between its ports. */
export const straightened = (route: Route): Route => {
  const { via: _dropped, ...rest } = route
  return rest
}

/** The segment of *course* nearest *point*, by its index. */
const segmentNearest = (course: readonly Point[], point: Point): number => {
  let best = 0
  let nearest = Number.POSITIVE_INFINITY
  course.slice(1).forEach((end, index) => {
    const start = course[index]
    const foot = footOn(start, end, point)
    const distance = distanceBetween(foot, point)
    if (distance < nearest) {
      nearest = distance
      best = index
    }
  })
  return best
}

const footOn = (start: Point, end: Point, point: Point): Point => {
  const length = distanceBetween(start, end)
  if (length === 0) return start
  const share = Math.max(0, Math.min(1,
    ((point.x - start.x) * (end.x - start.x) + (point.y - start.y) * (end.y - start.y)) / length ** 2))
  return { x: start.x + share * (end.x - start.x), y: start.y + share * (end.y - start.y) }
}

/** The whole route of *routed* with a bend added where *point* falls on its course: it stays until moved. */
export const withBendAdded = (routed: RoutedConnector, point: Point, stated?: Route): Route => {
  const whole = stated?.via?.length ? stated : statedWhole(routed, stated)
  const course = routed.course
  const index = segmentNearest(course, point)
  const added = footOn(course[index], course[index + 1], point)
  const along = (one: Point) => fractionAlong(course, one)
  const via = [...bendsShown(course, whole), added].sort((one, other) => along(one) - along(other))
  return { ...whole, via: via.map(bend) }
}

/** *route* without its bend *index*; without bends, straightened. */
export const withBendRemoved = (route: Route, index: number): Route => {
  const via = (route.via ?? []).filter((_, at) => at !== index)
  return via.length > 0 ? { ...route, via } : straightened(route)
}

/** *route* with its bend *index* at *point*: the course is completed through it at right angles. */
export const withBendAt = (route: Route, index: number, point: Point): Route =>
  ({ ...route, via: (route.via ?? []).map((one, at) => (at === index ? bend(point) : one)) })

const stubAt = (port: Point, side: Side, run: number): Point =>
  ({ x: port.x + OUTWARD[side][0] * run, y: port.y + OUTWARD[side][1] * run })

/**
 * The course of *routed* with its segment *index* moved sideways to *to* (a y for a level segment, an
 * x for an upright one). A segment out of a port takes a stub there first, so the end stays where it
 * is; a segment next to one stops where that end's run would grow shorter than it may be.
 */
export const segmentMoved = (
  routed: RoutedConnector, decorated: readonly [boolean, boolean], index: number, to: number,
): Point[] => {
  const course = routed.course.map((point) => ({ ...point }))
  const [start, end] = [course[index], course[index + 1]]
  const level = Math.abs(start.y - end.y) <= IN_LINE
  const axis: 'x' | 'y' = level ? 'y' : 'x'
  const runs = [runFor(decorated[0]), runFor(decorated[1])]
  let at = index
  if (at === course.length - 2) {
    const stub = stubAt(course[course.length - 1], routed.targetPort.side, runs[1])
    course.splice(course.length - 1, 0, { ...stub }, stub)
  }
  if (at === 0) {
    const stub = stubAt(course[0], routed.sourcePort.side, runs[0])
    course.splice(1, 0, stub, { ...stub })
    at = 2
  }
  let wanted = to
  for (const [which, port, side] of [[0, course[0], routed.sourcePort.side], [1, course[course.length - 1],
    routed.targetPort.side]] as const) {
    const next = which === 0 ? 1 : course.length - 2
    const touches = which === 0 ? at === next : at + 1 === next
    const outward = OUTWARD[side][axis === 'x' ? 0 : 1]
    if (!touches || outward === 0) continue
    const limit = port[axis] + outward * runs[which]
    wanted = outward > 0 ? Math.max(wanted, limit) : Math.min(wanted, limit)
  }
  course[at] = { ...course[at], [axis]: wanted }
  course[at + 1] = { ...course[at + 1], [axis]: wanted }
  return course
}

/**
 * *course* as a whole stated route between *routed*'s ports, tidied: a jog shorter than *jog* is
 * straightened by moving its far side onto its near one, and a corner in line with both neighbours
 * goes (sketch 02·4). What is left are the route's corners and nothing else.
 */
export const tidiedRoute = (course: readonly Point[], routed: RoutedConnector, jog: number, stated?: Route): Route => {
  const points = course.map((point) => ({ ...point }))
  for (let index = 1; index < points.length - 2; index += 1) {
    const [a, b] = [points[index], points[index + 1]]
    if (distanceBetween(a, b) >= jog || distanceBetween(a, b) === 0) continue
    const axis: 'x' | 'y' = Math.abs(a.y - b.y) <= IN_LINE ? 'x' : 'y'
    if (index + 2 < points.length - 1) {
      points[index + 1] = { ...b, [axis]: a[axis] }
      points[index + 2] = { ...points[index + 2], [axis]: a[axis] }
    } else if (index - 1 > 0) {
      points[index] = { ...a, [axis]: b[axis] }
      points[index - 1] = { ...points[index - 1], [axis]: b[axis] }
    }
  }
  const kept = [points[0]]
  for (let index = 1; index < points.length - 1; index += 1) {
    const [before, here, after] = [kept[kept.length - 1], points[index], points[index + 1]]
    const repeats = distanceBetween(before, here) <= IN_LINE
    const inLine = (Math.abs(before.x - here.x) <= IN_LINE && Math.abs(here.x - after.x) <= IN_LINE)
      || (Math.abs(before.y - here.y) <= IN_LINE && Math.abs(here.y - after.y) <= IN_LINE)
    if (!repeats && !inLine) kept.push(here)
  }
  return {
    ...(stated?.label ? { label: stated.label } : {}),
    from: routed.sourcePort, to: routed.targetPort, via: kept.slice(1).map(bend),
  }
}

/** The anchor that sets a label's centre at *centre*: the nearest place along *course*, and the offset from it. */
export const labelAnchoredAt = (course: readonly Point[], centre: Point): LabelAnchor => {
  const at = halfUp(fractionAlong(course, centre) * 1000) / 1000
  const base = pointAlong(course, at)
  return { at, dx: halfUp(centre.x - base.x), dy: halfUp(centre.y - base.y) }
}

/** Where a label anchored at *anchor* on *course* is centred. */
export const labelCentre = (course: readonly Point[], anchor: LabelAnchor): Point => {
  const base = pointAlong(course, anchor.at)
  return { x: base.x + anchor.dx, y: base.y + anchor.dy }
}

/**
 * The line end nearest *point* within *within*, as the line's place and which end: a press there picks
 * the line rather than the element it ends on (Q33).
 */
export const lineEndNear = (
  courses: ReadonlyMap<number, readonly Point[]>, point: Point, within: number,
): { readonly line: number; readonly end: End } | null => {
  let found: { line: number; end: End } | null = null
  let nearest = within
  for (const [line, course] of courses) {
    if (course.length < 2) continue
    for (const [end, at] of [['from', course[0]], ['to', course[course.length - 1]]] as const) {
      const distance = distanceBetween(at, point)
      if (distance <= nearest) {
        nearest = distance
        found = { line, end }
      }
    }
  }
  return found
}

/** *arrangement* with the line *key* stating *route*; a route that states nothing is no entry. */
export const withRouteStated = (arrangement: Arrangement, key: string, route: Route): Arrangement => {
  const routes = new Map(arrangement.routes)
  if (route.from || route.to || route.via?.length || route.label) routes.set(key, route)
  else routes.delete(key)
  return { ...arrangement, routes }
}
