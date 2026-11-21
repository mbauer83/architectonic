/**
 * The lab's picture as the router sees it, and the router's two passes over it.
 *
 * The scene is the one the composer routes (`arrangement.py`): every element, every box, and the text
 * a line keeps out of — each box's title band carried with the box's top, and each label set outside
 * its element carried with the element. A connector is one drawn line, from its stated source to its
 * stated target. Only the router's public passes are called: `routeAll` with no quick pass on a drop,
 * and with one while something is dragged.
 */
import type { Extent } from '../geometry'
import { routeAll } from '../routing/router'
import type { Connector, RoutedConnector, RoutingResult, RoutingScene } from '../routing/scene'
import type { Arrangement } from './labArrangement'
import { fittedBoxes } from './labArrangement'
import type { LabGeometry } from './labGeometry'

/** Where every shape is now, elements and boxes apart, as the router and the drawing both need. */
export interface Placement {
  readonly elements: ReadonlyMap<string, Extent>
  readonly boxes: ReadonlyMap<string, Extent>
}

export const placementOf = (geometry: LabGeometry, arrangement: Arrangement): Placement => ({
  elements: arrangement.elements,
  boxes: fittedBoxes(geometry, arrangement),
})

const SAME = 0.5

const resizedFromDrawn = (now: Extent, drawn: Extent): boolean =>
  Math.abs(now.right - now.left - (drawn.right - drawn.left)) > SAME ||
  Math.abs(now.bottom - now.top - (drawn.bottom - drawn.top)) > SAME

/** The text a line keeps out of, where it is now. */
export const textRegions = (geometry: LabGeometry, placement: Placement): ReadonlyMap<string, Extent> => {
  const regions = new Map<string, Extent>()
  for (const box of geometry.boxes) {
    const now = placement.boxes.get(box.alias)
    if (!box.title_band || !now) continue
    regions.set(`band:${box.alias}`, {
      left: now.left, top: now.top, right: now.right, bottom: now.top + (box.title_band.bottom - box.extent.top),
    })
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

export const sceneOf = (geometry: LabGeometry, placement: Placement): RoutingScene => ({
  elements: placement.elements,
  boxes: placement.boxes,
  text: textRegions(geometry, placement),
  fixedLines: [],
})

/** Every drawn line as a connector, keyed by its place on the picture as the composer keys it. */
export const connectorsOf = (geometry: LabGeometry): Connector[] =>
  geometry.relations.map((relation) => ({
    key: String(relation.index),
    source: relation.source,
    target: relation.target,
    decorated: relation.decorated,
  }))

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

/** Every line routed afresh: what a drop asks for. */
export const fullPass = (geometry: LabGeometry, placement: Placement): RoutingResult =>
  routeAll(sceneOf(geometry, placement), connectorsOf(geometry))

/** Only the lines of the shapes in *changed* routed again, the rest kept from *previous*: a drag frame. */
export const quickPass = (
  geometry: LabGeometry,
  placement: Placement,
  previous: ReadonlyMap<string, RoutedConnector>,
  changed: ReadonlySet<string>,
): RoutingResult => routeAll(sceneOf(geometry, placement), connectorsOf(geometry), { previous, changed })
