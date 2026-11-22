/**
 * The lab's picture as the router sees it, and the router's two passes over it.
 *
 * The scene is the one the composer routes (`arrangement.py`): every element, every box, and the text
 * a line keeps out of — each box's title band as wide as its title, carried as the title is, and each
 * label set outside its element carried with the element. A connector is one drawn line, from its stated source to its
 * stated target. Only the router's public passes are called: `routeAll` with no quick pass on a drop,
 * and with one while something is dragged.
 */
import type { Extent } from '../geometry'
import { routeAll } from '../routing/router'
import { widened } from '../routing/widening'
import type { Connector, RoutedConnector, RoutingResult, RoutingScene } from '../routing/scene'
import { sameExtent } from '../routing/scene'
import type { Arrangement } from './labArrangement'
import { fittedBoxes } from './labArrangement'
import { BAND_MARGIN } from '../routeQuality'
import type { GeometryBox, LayoutGeometry } from '../../schemas/diagramLayoutGeometry'

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
 * width included (`dragRegionOf` in the lab's drawing).
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

export const sceneOf = (geometry: LayoutGeometry, placement: Placement): RoutingScene => ({
  elements: placement.elements,
  boxes: placement.boxes,
  text: textRegions(geometry, placement),
  fixedLines: [],
})

/** Every drawn line as a connector, keyed by its place on the picture as the composer keys it. */
export const connectorsOf = (geometry: LayoutGeometry): Connector[] =>
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

/**
 * *arrangement* with every channel too narrow for its lines opened (`routing/widening`), as the first
 * layout a diagram writes down is: elements where the widening put them, and each box it grew stated
 * at the size it grew to.
 */
export const widenedArrangement = (geometry: LayoutGeometry, arrangement: Arrangement): Arrangement => {
  const placement = placementOf(geometry, arrangement)
  const opened = widened(sceneOf(geometry, placement), connectorsOf(geometry))
  const before = placement.boxes
  return {
    elements: new Map(opened.elements),
    stated: new Map([
      ...arrangement.stated,
      ...[...opened.boxes].filter(([alias, extent]) => {
        const was = before.get(alias)
        return !was || !sameExtent(was, extent)
      }),
    ]),
  }
}

/** Every line routed afresh: what a drop asks for. */
export const fullPass = (geometry: LayoutGeometry, placement: Placement): RoutingResult =>
  routeAll(sceneOf(geometry, placement), connectorsOf(geometry))

/** Only the lines of the shapes in *changed* routed again, the rest kept from *previous*: a drag frame. */
export const quickPass = (
  geometry: LayoutGeometry,
  placement: Placement,
  previous: ReadonlyMap<string, RoutedConnector>,
  changed: ReadonlySet<string>,
): RoutingResult => routeAll(sceneOf(geometry, placement), connectorsOf(geometry), { previous, changed })
