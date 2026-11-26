/**
 * Lines that follow what a drag moved, routing nothing (plan D5: I3, then I4).
 *
 * - **A frame** (`followPass`): each line of a moved shape follows it from the course shown when the drag
 *   began, keeping its shape; every other line stays as shown. What a frame can afford on a picture of
 *   hundreds of lines.
 * - **The drop** (`followedCleanly`): of the lines something moved touches, those whose followed course
 *   breaks no hard rule more than their shown course did keep it. Only the rest go to the router (I5) —
 *   so a move routes the few lines it put something in the way of, not every line it touches, and a line
 *   PlantUML drew along another may still run so, as it was shown.
 */
import type { Extent, Point } from './geometry'
import { courseOf } from './orthogonal'
import type { Route } from './orthogonal'
import { elementsCrossed, reattached } from './attachment'
import { statedWhole } from './canvasRouteEdits'
import { bendsAtEnds, runIndex, runsAlongIn, textsCrossed } from './routeQuality'
import type { ShownLine } from './routing/kept'
import type { RoutedConnector, RoutingResult } from './routing/scene'
import type { Placement, StatedRoutes } from './canvasRouting'
import type { LayoutGeometry } from '../schemas/diagramLayoutGeometry'

/** One state of the picture as following asks it: where the shapes are, the stated courses, the text. */
export interface Pictured {
  readonly placement: Placement
  /** The course of each line that states its bends, by its place on the picture. */
  readonly stated: ReadonlyMap<number, readonly Point[]>
  readonly text: ReadonlyMap<string, Extent>
}

const extentIn = (placement: Placement, alias: string): Extent | undefined =>
  placement.elements.get(alias) ?? placement.boxes.get(alias)

/** *shown* where its ends are now: as its stated bends run where it states them, else followed. */
const following = (stated: Route | undefined, shown: RoutedConnector, source: Extent, target: Extent): Route =>
  (stated?.via?.length && stated.from && stated.to ? stated : reattached(statedWhole(shown), source, target))

/**
 * A drag frame's lines: each line of a shape in *changed* follows it from the course *previous* showed,
 * a line with stated bends runs them where its ends are now, and every other line is *previous*'s own.
 */
export const followPass = (
  geometry: LayoutGeometry, placement: Placement, routes: StatedRoutes, previous: RoutingResult,
  changed: ReadonlySet<string>,
): RoutingResult => {
  const lines = new Map(previous.routes)
  for (const relation of geometry.relations) {
    if (!changed.has(relation.source) && !changed.has(relation.target)) continue
    const key = String(relation.index)
    const [source, target] = [extentIn(placement, relation.source), extentIn(placement, relation.target)]
    const shown = previous.routes.get(key)
    if (!source || !target || !shown) continue
    const route = following(relation.key === undefined ? undefined : routes.get(relation.key), shown, source, target)
    const course = courseOf(route, source, target)
    if (course && route.from && route.to) lines.set(key, { key, sourcePort: route.from, targetPort: route.to, course })
  }
  return { ...previous, routes: lines }
}

/** What one line's course breaks of the hard rules, each counted: what following it may not add to. */
interface HardRules {
  readonly elements: number
  readonly text: number
  readonly bends: number
  readonly along: number
}

/** The hard rules each line in *asked* breaks in *pictured*, its lines running *courses*. */
const hardRulesOf = (
  geometry: LayoutGeometry, pictured: Pictured, courses: ReadonlyMap<number, readonly Point[]>,
  asked: readonly number[],
): ReadonlyMap<number, HardRules> => {
  const { placement, text } = pictured
  const runs = runIndex(courses, [...placement.elements.values(), ...placement.boxes.values()])
  const relations = new Map(geometry.relations.map((relation) => [relation.index, relation]))
  return new Map(asked.flatMap((index): [number, HardRules][] => {
    const [relation, course] = [relations.get(index), courses.get(index)]
    return relation && course ? [[index, {
      elements: elementsCrossed(course, placement.elements, [relation.source, relation.target]).length,
      text: textsCrossed(course, text).length,
      bends: bendsAtEnds(course, relation.decorated).length,
      along: runsAlongIn(course, runs, index).length,
    }]] : []
  }))
}

/** Every line's course in *pictured*: *shown*, those stating their bends as stated, then *these*. */
const coursesIn = (
  pictured: Pictured, shown: ReadonlyMap<string, RoutedConnector>,
  these: ReadonlyMap<number, readonly Point[]> = new Map(),
): ReadonlyMap<number, readonly Point[]> => new Map<number, readonly Point[]>([
  ...[...shown].map(([key, one]): [number, readonly Point[]] => [Number(key), one.course]),
  ...pictured.stated, ...these,
])

const noWorse = (then: HardRules | undefined, now: HardRules | undefined): boolean =>
  then !== undefined && now !== undefined && now.elements <= then.elements && now.text <= then.text
  && now.bends <= then.bends && now.along <= then.along

/**
 * Of *touched* — lines no stated route decides that something moved from *before* to *now* touches —
 * each whose course *previous* showed, followed to where its ends are now, breaks no hard rule more than
 * it did: through no further element or text, no new bend at a decorated end, along no further line or
 * border. By its place on the picture, with the course it follows.
 */
export const followedCleanly = (
  geometry: LayoutGeometry, before: Pictured, now: Pictured, previous: ReadonlyMap<string, RoutedConnector>,
  touched: readonly ShownLine[],
): ReadonlyMap<number, readonly Point[]> => {
  if (touched.length === 0) return new Map()
  const followed = new Map(touched.flatMap((line): [number, Point[]][] => {
    const [source, target] = [extentIn(now.placement, line.source), extentIn(now.placement, line.target)]
    const shown = previous.get(line.key)
    if (!source || !target || !shown) return []
    const course = courseOf(following(undefined, shown, source, target), source, target)
    return course && course.length >= 2 ? [[Number(line.key), course]] : []
  }))
  const asked = [...followed.keys()]
  const was = hardRulesOf(geometry, before, coursesIn(before, previous), asked)
  const after = hardRulesOf(geometry, now, coursesIn(now, previous, followed), asked)
  return new Map([...followed].filter(([index]) => noWorse(was.get(index), after.get(index))))
}
