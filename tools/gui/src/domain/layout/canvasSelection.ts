/**
 * What a selection rectangle chooses, and which of a selection the arranging commands act on.
 *
 * A rectangle selects the elements it encloses — or, by preference, those it touches — and only the
 * boxes it wholly encloses: a box it merely touches is the ground it was drawn on, not something chosen
 * (sketch 02·8), and the bends a line states inside it — moved with the selection, nudged, removed.
 * Align and distribute act on elements only, as the server's intents do; a box moves with its members.
 */
import type { Extent } from './geometry'
import { encloses, overlaps } from './geometry'
import type { Route } from './orthogonal'
import type { AlignEdge, DistributeAxis } from './layoutIntents'
import { LEAST_TO_ALIGN, LEAST_TO_DISTRIBUTE, aligned, distributed } from './layoutIntents'
import type { LayoutGeometry } from '../schemas/diagramLayoutGeometry'
import type { Arrangement } from './canvasArrangement'
import { descendantsOf, placedAt } from './canvasArrangement'
import { withBendRemoved, withRouteStated } from './canvasRouteEdits'
import type { Placement } from './canvasRouting'

/** Whether a rectangle selects the elements it encloses, or every element it touches. */
export type RectangleRule = 'encloses' | 'touches'

/** The shapes *rectangle* selects: elements by *rule*, boxes only when wholly inside it. */
export const chosenBy = (rectangle: Extent, placement: Placement, rule: RectangleRule = 'encloses'): string[] => {
  const hit = rule === 'encloses' ? (extent: Extent) => encloses(rectangle, extent)
    : (extent: Extent) => overlaps(rectangle, extent)
  return [
    ...[...placement.elements].filter(([, extent]) => hit(extent)).map(([alias]) => alias),
    ...[...placement.boxes].filter(([, extent]) => encloses(rectangle, extent)).map(([alias]) => alias),
  ]
}

/** *selection* with *alias* taken out where it is in, and added where it is not. */
export const toggled = (selection: readonly string[], alias: string): string[] =>
  selection.includes(alias) ? selection.filter((one) => one !== alias) : [...selection, alias]

/** The elements of *selection* where they are now, by alias: what align and distribute move. */
export const elementsOf = (selection: readonly string[], placement: Placement): ReadonlyMap<string, Extent> =>
  new Map(selection.flatMap((alias) => {
    const extent = placement.elements.get(alias)
    return extent ? [[alias, extent] as const] : []
  }))

/**
 * *arrangement* with the elements of *selection* aligned on *edge*, each carrying what it holds; as it
 * was where fewer than two are elements.
 */
export const alignedSelection = (
  geometry: LayoutGeometry, arrangement: Arrangement, placement: Placement, selection: readonly string[],
  edge: AlignEdge,
): Arrangement => {
  const elements = elementsOf(selection, placement)
  return elements.size < LEAST_TO_ALIGN ? arrangement : placedAt(geometry, arrangement, aligned(elements, edge))
}

/**
 * *arrangement* with the elements of *selection* distributed along *axis*, the outer two kept; as it
 * was where fewer than three are elements.
 */
export const distributedSelection = (
  geometry: LayoutGeometry, arrangement: Arrangement, placement: Placement, selection: readonly string[],
  axis: DistributeAxis,
): Arrangement => {
  const elements = elementsOf(selection, placement)
  return elements.size < LEAST_TO_DISTRIBUTE ? arrangement
    : placedAt(geometry, arrangement, distributed(elements, axis))
}

/** A bend a line states, by the relation's key and the bend's place along it. */
export interface BendRef {
  readonly key: string
  readonly index: number
}

/** The bends the lines of *routes* state inside *rectangle*. */
export const bendsWithin = (rectangle: Extent, routes: ReadonlyMap<string, Route>): BendRef[] =>
  [...routes].flatMap(([key, route]) => (route.via ?? []).flatMap(([x, y], index) =>
    (x >= rectangle.left && x <= rectangle.right && y >= rectangle.top && y <= rectangle.bottom
      ? [{ key, index }] : [])))

/** *selection* with *more* added where it is not in it already. */
export const withBends = (selection: readonly BendRef[], more: readonly BendRef[]): BendRef[] =>
  [...selection, ...more.filter((one) => !selection.some((had) => had.key === one.key && had.index === one.index))]

/**
 * *arrangement* with the bends of *bends* moved by (dx, dy) — except on a line whose two ends move with
 * *carried*, which moves whole, bends and all.
 */
export const withBendsMoved = (
  geometry: LayoutGeometry, arrangement: Arrangement, bends: readonly BendRef[], carried: readonly string[],
  dx: number, dy: number,
): Arrangement => {
  const moving = new Set(carried.flatMap((alias) => [alias, ...descendantsOf(geometry, alias)]))
  const whole = new Set(geometry.relations.flatMap((relation) =>
    (relation.key !== undefined && moving.has(relation.source) && moving.has(relation.target) ? [relation.key] : [])))
  return bends.filter((bend) => !whole.has(bend.key)).reduce((now, { key, index }) => {
    const route = now.routes.get(key)
    const via = route?.via
    if (!route || !via?.[index]) return now
    const [x, y] = via[index]
    return withRouteStated(now, key, { ...route, via: via.map((bend, at) => (at === index ? [x + dx, y + dy] : bend)) })
  }, arrangement)
}

/** *arrangement* without the bends of *bends*: each line's own, from the last back, so places stay true. */
export const withoutBends = (arrangement: Arrangement, bends: readonly BendRef[]): Arrangement =>
  [...bends].sort((one, other) => other.index - one.index).reduce((now, { key, index }) => {
    const route = now.routes.get(key)
    return route?.via?.[index] ? withRouteStated(now, key, withBendRemoved(route, index)) : now
  }, arrangement)
