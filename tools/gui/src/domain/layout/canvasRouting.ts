/**
 * The canvas's picture as the router sees it, and the router's two passes over it.
 *
 * The scene is the one the composer routes (`arrangement.py`): every element, every box, and the text
 * a line keeps out of — each box's title band as wide as its title, carried as the title is, and each
 * label set outside its element carried with the element. A connector is one drawn line, from its stated source to its
 * stated target. Only the router's public passes are called: `routeAll` with no quick pass when a
 * picture is opened, and with one while something is dragged.
 *
 * A relation's stated route is read as the composer reads it (`_Arranging.routing`): one that states
 * its bends between two stated ports runs them, a fixed line the others go round; one that states
 * only ports is routed between them; one that states neither keeps the line shown while nothing that
 * moved touches it (`routing/kept`), a fixed line too.
 */
import type { Extent, Point } from './geometry'
import type { Route } from './orthogonal'
import { courseOf } from './orthogonal'
import type { QuickPass } from './routing/router'
import { routeAll } from './routing/router'
import type { ShownLine } from './routing/kept'
import { attached, keptLines } from './routing/kept'
import type { Connector, RoutedConnector, RoutingResult, RoutingScene } from './routing/scene'
import { byText } from './routing/scene'
import type { Arrangement } from './canvasArrangement'
import { drawnArrangement, fittedBoxes } from './canvasArrangement'
import { portNear } from './canvasRouteEdits'
import { BAND_MARGIN } from './routeQuality'
import type { GeometryBox, GeometryRelation, LayoutGeometry } from '../schemas/diagramLayoutGeometry'
import { pointsOf } from '../schemas/diagramLayoutGeometry'

/** Where every shape is now, elements and boxes apart, as the router and the drawing both need. */
export interface Placement {
  readonly elements: ReadonlyMap<string, Extent>
  readonly boxes: ReadonlyMap<string, Extent>
}

export const placementOf = (geometry: LayoutGeometry, arrangement: Arrangement): Placement => ({
  elements: arrangement.elements,
  boxes: fittedBoxes(geometry, arrangement),
})

const SAME = 0.5

/** Whether *now* is another size than the shape was *drawn* at: resized, not only moved. */
export const resizedFromDrawn = (now: Extent, drawn: Extent): boolean =>
  Math.abs(now.right - now.left - (drawn.right - drawn.left)) > SAME ||
  Math.abs(now.bottom - now.top - (drawn.bottom - drawn.top)) > SAME

/**
 * A box's title band as a line keeps out of it, where the box is now — for routing only. As wide as its
 * title with BAND_MARGIN either side (`text_clearance.title_band`), carried with the box's top and
 * middle as the title is drawn, within the box. A band the box's whole width would leave a line from
 * outside no way in but round the side.
 *
 * Not where the box is taken to drag it: that is its whole outline, the title band across its full
 * width included (`dragRegionOf` on the canvas's drawing).
 */
export const routingBandOf = (box: GeometryBox, now: Extent): Extent | null => {
  if (!box.title_band || box.words.length === 0) return null
  const dx = (now.left + now.right) / 2 - (box.extent.left + box.extent.right) / 2
  const left = Math.min(...box.words.map((word) => word.x)) + dx - BAND_MARGIN
  const right = Math.max(...box.words.map((word) => word.x + word.width)) + dx + BAND_MARGIN
  return {
    left: Math.max(now.left, left),
    top: now.top,
    right: Math.min(now.right, right),
    bottom: now.top + (box.title_band.bottom - box.extent.top),
  }
}

/** The text a line keeps out of, where it is now. */
export const textRegions = (geometry: LayoutGeometry, placement: Placement): ReadonlyMap<string, Extent> => {
  const regions = new Map<string, Extent>()
  for (const box of geometry.boxes) {
    const now = placement.boxes.get(box.alias)
    const band = now ? routingBandOf(box, now) : null
    if (band) regions.set(`band:${box.alias}`, band)
  }
  for (const element of geometry.elements) {
    const now = placement.elements.get(element.alias)
    const label = element.outside_label
    if (!label || !now || resizedFromDrawn(now, element.extent)) continue
    const dx = now.left - element.extent.left
    const dy = now.top - element.extent.top
    regions.set(`label:${element.alias}`, {
      left: label.left + dx, top: label.top + dy, right: label.right + dx, bottom: label.bottom + dy,
    })
  }
  return regions
}

/** Each drawn relation's stated route, by relation key: what the user shaped. */
export type StatedRoutes = ReadonlyMap<string, Route>

const NONE: StatedRoutes = new Map()

/**
 * The course of every relation whose route states its bends between two stated ports, by its place on
 * the picture: the line it runs, which the router routes the others round.
 */
export const statedCourses = (
  geometry: LayoutGeometry, placement: Placement, routes: StatedRoutes = NONE,
): ReadonlyMap<number, Point[]> => {
  const extentOf = (alias: string): Extent | undefined => placement.elements.get(alias) ?? placement.boxes.get(alias)
  return new Map(geometry.relations.flatMap((relation): [number, Point[]][] => {
    const route = relation.key === undefined ? undefined : routes.get(relation.key)
    const [source, target] = [extentOf(relation.source), extentOf(relation.target)]
    const course = route?.via?.length && source && target ? courseOf(route, source, target) : null
    return course && course.length >= 2 ? [[relation.index, course]] : []
  }))
}

export const sceneOf = (
  geometry: LayoutGeometry, placement: Placement, fixed: ReadonlyMap<number, readonly Point[]> = new Map(),
): RoutingScene => ({
  elements: placement.elements,
  boxes: placement.boxes,
  text: textRegions(geometry, placement),
  fixedLines: [...fixed.values()],
})

/**
 * Every drawn line the router routes as a connector, keyed by its place on the picture as the composer
 * keys it, with the ports its route states; a line in *fixed* runs its stated course instead.
 */
export const connectorsOf = (
  geometry: LayoutGeometry, routes: StatedRoutes = NONE, fixed: ReadonlyMap<number, unknown> = new Map(),
): Connector[] =>
  geometry.relations.filter((relation) => !fixed.has(relation.index)).map((relation) => {
    const route = relation.key === undefined ? undefined : routes.get(relation.key)
    return {
      key: String(relation.index),
      source: relation.source,
      target: relation.target,
      decorated: relation.decorated,
      ...(route?.from ? { sourcePort: route.from } : {}),
      ...(route?.to ? { targetPort: route.to } : {}),
    }
  })

/** The shapes, elements and boxes alike, that sit or measure differently in *after* than in *before*. */
export const changedShapes = (before: Placement, after: Placement): Set<string> => {
  const differs = (one: Extent | undefined, other: Extent | undefined): boolean =>
    !one || !other || one.left !== other.left || one.top !== other.top ||
    one.right !== other.right || one.bottom !== other.bottom
  return new Set(
    [...after.elements, ...after.boxes]
      .filter(([alias, extent]) => differs(before.elements.get(alias) ?? before.boxes.get(alias), extent))
      .map(([alias]) => alias),
  )
}

/** *result* with each line that runs its stated course in it as routed: every line's course in one place. */
const withFixed = (
  result: RoutingResult, geometry: LayoutGeometry, routes: StatedRoutes, fixed: ReadonlyMap<number, Point[]>,
): RoutingResult => {
  if (fixed.size === 0) return result
  const lines = new Map(result.routes)
  for (const relation of geometry.relations) {
    const course = fixed.get(relation.index)
    const route = relation.key === undefined ? undefined : routes.get(relation.key)
    if (!course || !route?.from || !route.to) continue
    const key = String(relation.index)
    lines.set(key, { key, sourcePort: route.from, targetPort: route.to, course })
  }
  return { ...result, routes: lines }
}

/** Each line no stated route decides — no ports, no bends — with the course *shown* gives it. */
const unstatedLines = (
  geometry: LayoutGeometry, routes: StatedRoutes, shown: (relation: GeometryRelation) => readonly Point[] | undefined,
): ShownLine[] => geometry.relations.flatMap((relation) => {
  const route = relation.key === undefined ? undefined : routes.get(relation.key)
  const course = route?.from || route?.to || route?.via?.length ? undefined : shown(relation)
  return course && course.length >= 2
    ? [{ key: String(relation.index), source: relation.source, target: relation.target, course }] : []
})

/** *result* with each kept line in it as shown, its ports read off where it meets its ends. */
const withKept = (
  result: RoutingResult, geometry: LayoutGeometry, placement: Placement, kept: ReadonlyMap<number, readonly Point[]>,
): RoutingResult => {
  if (kept.size === 0) return result
  const extentOf = (alias: string): Extent | undefined => placement.elements.get(alias) ?? placement.boxes.get(alias)
  const lines = new Map(result.routes)
  for (const relation of geometry.relations) {
    const course = kept.get(relation.index)
    const [source, target] = [extentOf(relation.source), extentOf(relation.target)]
    if (!course || !source || !target) continue
    const key = String(relation.index)
    lines.set(key, {
      key, sourcePort: portNear(source, course[0]), targetPort: portNear(target, course[course.length - 1]),
      course: [...course],
    })
  }
  return { ...result, routes: new Map([...lines].sort(([one], [other]) => byText(one, other))) }
}

/** Every line not *kept* routed, those with stated bends run as stated, the kept ones as shown. */
const routedKeeping = (
  geometry: LayoutGeometry, placement: Placement, routes: StatedRoutes,
  kept: ReadonlyMap<number, readonly Point[]>, quick: QuickPass | null,
): RoutingResult => {
  const fixed = statedCourses(geometry, placement, routes)
  const extentOf = (alias: string): Extent | undefined => placement.elements.get(alias) ?? placement.boxes.get(alias)
  const onBorders = new Map(geometry.relations.flatMap((relation): [number, readonly Point[]][] => {
    const [course, source, target] = [kept.get(relation.index), extentOf(relation.source), extentOf(relation.target)]
    return course && source && target ? [[relation.index, attached(course, source, target)]] : []
  }))
  const still = new Map<number, readonly Point[]>([...fixed, ...onBorders])
  const result = routeAll(sceneOf(geometry, placement, still), connectorsOf(geometry, routes, still), quick)
  return withKept(withFixed(result, geometry, routes, fixed), geometry, placement, onBorders)
}

/** The courses of *lines* that *keep* names, by their place on the picture. */
const coursesOf = (lines: readonly ShownLine[], keep: ReadonlySet<string>): ReadonlyMap<number, readonly Point[]> =>
  new Map(lines.filter((line) => keep.has(line.key)).map((line) => [Number(line.key), line.course]))

/**
 * The picture's lines where *placement* puts its shapes: PlantUML's own line wherever nothing that
 * moved since it drew them touches it (`keptLines`), those with stated bends as stated, and the rest
 * routed. What opening or taking over a picture shows, and what the composer draws of a stored layout.
 */
export const fullPass = (
  geometry: LayoutGeometry, placement: Placement, routes: StatedRoutes = NONE,
): RoutingResult => {
  const drawn = placementOf(geometry, drawnArrangement(geometry))
  const lines = unstatedLines(geometry, routes, (relation) => pointsOf(relation.course))
  const kept = keptLines(sceneOf(geometry, drawn), sceneOf(geometry, placement), lines)
  return routedKeeping(geometry, placement, routes, coursesOf(lines, kept), null)
}

/**
 * Only the lines touching what moved from *before* to *placement* (`keptLines`), the lines of the shapes
 * in *changed* and the lines *rerouted* names by their place routed again; the rest kept as *previous*
 * showed them: a drag frame, or any change after one, so a line keeps the course it was shown with until
 * something moves it.
 */
export const quickPass = (
  geometry: LayoutGeometry,
  before: Placement,
  placement: Placement,
  routes: StatedRoutes,
  previous: ReadonlyMap<string, RoutedConnector>,
  changed: ReadonlySet<string>,
  rerouted: ReadonlySet<string> = new Set(),
): RoutingResult => {
  const lines = unstatedLines(geometry, routes, (relation) =>
    (rerouted.has(String(relation.index)) ? undefined : previous.get(String(relation.index))?.course))
  const kept = keptLines(sceneOf(geometry, before), sceneOf(geometry, placement), lines)
  const others = new Map([...previous].filter(([key]) => !rerouted.has(key) && !kept.has(key)))
  return routedKeeping(geometry, placement, routes, coursesOf(lines, kept), { previous: others, changed })
}
