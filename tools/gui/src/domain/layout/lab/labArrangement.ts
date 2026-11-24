/**
 * Where everything on a picture being arranged is after the moves and resizes made so far. The layout
 * block that states it is `arrangementLayout`'s to write.
 *
 * The box rule is the composer's (`src/infrastructure/rendering/layout/arrangement.py`): a box is what
 * its contents need with the padding PlantUML gave it, never narrower than its title, widened to what
 * is stated for it and never narrowed. So a member stays inside its box because the box grows to hold
 * it, and moving a box moves what it holds. Membership never changes here: which box an element is in
 * is the diagram's to say, not a drag's.
 */
import type { Extent, Point } from '../geometry'
import { unionOf, widthOf } from '../geometry'
import { reattached } from '../attachment'
import type { Route } from '../orthogonal'
import type { GeometryBox, LayoutGeometry, MeasuredWord } from '../../schemas/diagramLayoutGeometry'

/**
 * What has been moved, resized or shaped: every element where it is now, each box stated by size, and
 * each drawn relation's stated route by relation key — the ports, bends and label anchor the user set,
 * which the router keeps.
 */
export interface Arrangement {
  readonly elements: ReadonlyMap<string, Extent>
  readonly stated: ReadonlyMap<string, Extent>
  readonly routes: ReadonlyMap<string, Route>
}

/** The least room kept either side of a box's title. */
const TITLE_MARGIN = 8

/** The smallest an element may be resized to, either way. */
export const SMALLEST_ELEMENT = 24

export const translated = (extent: Extent, dx: number, dy: number): Extent => ({
  left: extent.left + dx,
  top: extent.top + dy,
  right: extent.right + dx,
  bottom: extent.bottom + dy,
})

/** PlantUML's arrangement: every element where it drew it, nothing stated. */
export const drawnArrangement = (geometry: LayoutGeometry): Arrangement => ({
  elements: new Map(geometry.elements.map((element) => [element.alias, element.extent])),
  stated: new Map(),
  routes: new Map(),
})

/** Every shape's alias under the box it is drawn directly inside; `null` for the canvas. */
export const childrenOf = (geometry: LayoutGeometry): ReadonlyMap<string | null, readonly string[]> => {
  const children = new Map<string | null, string[]>()
  for (const shape of [...geometry.boxes, ...geometry.elements]) {
    const parent = shape.inside ?? null
    children.set(parent, [...(children.get(parent) ?? []), shape.alias])
  }
  return children
}

const acrossWords = (words: readonly MeasuredWord[]): readonly [number, number] | null =>
  words.length === 0
    ? null
    : [Math.min(...words.map((word) => word.x)), Math.max(...words.map((word) => word.x + word.width))]

const wideEnoughForItsTitle = (needed: Extent, box: GeometryBox): Extent => {
  const across = acrossWords(box.words)
  if (!across) return needed
  const drawn = box.extent
  const margin = Math.max(TITLE_MARGIN, Math.min(across[0] - drawn.left, drawn.right - across[1]))
  const least = across[1] - across[0] + 2 * margin
  if (widthOf(needed) >= least) return needed
  const grow = (least - widthOf(needed)) / 2
  return { ...needed, left: needed.left - grow, right: needed.right + grow }
}

/** Every box where it is drawn now, given where the elements are and what is stated for boxes. */
export const fittedBoxes = (geometry: LayoutGeometry, arrangement: Arrangement): ReadonlyMap<string, Extent> => {
  const children = childrenOf(geometry)
  const boxes = new Map(geometry.boxes.map((box) => [box.alias, box]))
  const drawn = new Map(
    [...geometry.elements, ...geometry.boxes].map((shape) => [shape.alias, shape.extent] as const),
  )
  const fitted = new Map<string, Extent>()
  const now = (alias: string): Extent =>
    arrangement.elements.get(alias) ?? fit(alias)
  const fit = (alias: string): Extent => {
    const known = fitted.get(alias)
    if (known) return known
    const box = boxes.get(alias)
    if (!box) return drawn.get(alias) as Extent
    const inside = children.get(alias) ?? []
    let needed = box.extent
    if (inside.length > 0) {
      const before = unionOf(inside.map((child) => drawn.get(child) as Extent))
      const after = unionOf(inside.map(now))
      needed = {
        left: after.left - (before.left - box.extent.left),
        top: after.top - (before.top - box.extent.top),
        right: after.right + (box.extent.right - before.right),
        bottom: after.bottom + (box.extent.bottom - before.bottom),
      }
    }
    needed = wideEnoughForItsTitle(needed, box)
    const stated = arrangement.stated.get(alias)
    const result = stated ? unionOf([needed, stated]) : needed
    fitted.set(alias, result)
    return result
  }
  for (const box of geometry.boxes) fit(box.alias)
  return fitted
}

/** Every shape drawn inside *alias*, at any depth. */
export const descendantsOf = (geometry: LayoutGeometry, alias: string): readonly string[] => {
  const children = childrenOf(geometry)
  const walk = (parent: string): string[] =>
    (children.get(parent) ?? []).flatMap((child) => [child, ...walk(child)])
  return walk(alias)
}

/**
 * *arrangement* with the shapes *aliases* moved together by (dx, dy): a box carries everything it holds,
 * and a shape both chosen and carried moves once.
 */
export const movedTogether = (
  geometry: LayoutGeometry, arrangement: Arrangement, aliases: readonly string[], dx: number, dy: number,
): Arrangement => {
  const carried = new Set(aliases.flatMap((alias) => [alias, ...descendantsOf(geometry, alias)]))
  const shift = (entries: ReadonlyMap<string, Extent>): Map<string, Extent> =>
    new Map([...entries].map(([key, extent]) => [key, carried.has(key) ? translated(extent, dx, dy) : extent]))
  const elements = shift(arrangement.elements)
  return {
    elements, stated: shift(arrangement.stated),
    routes: routesFollowing(geometry, arrangement.routes, elements, carried, [dx, dy]),
  }
}

/**
 * *routes* once the shapes *changed* have moved, by *shift* where they were only moved, to where
 * *elements* says: a stated route whose two ends moved together moves with them, bends and all; one
 * with a single end among them keeps its shape and stays attached (`reattached`, I3 then I4). A route
 * that states no bends has nothing to carry: its ports ride on their elements.
 */
const routesFollowing = (
  geometry: LayoutGeometry, routes: ReadonlyMap<string, Route>, elements: ReadonlyMap<string, Extent>,
  changed: ReadonlySet<string>, shift: readonly [number, number] | null,
): ReadonlyMap<string, Route> => {
  if (routes.size === 0) return routes
  const ends = new Map(geometry.relations.flatMap((one) => (one.key === undefined ? [] : [[one.key, one] as const])))
  return new Map([...routes].map(([key, route]) => {
    const relation = ends.get(key)
    if (!relation || !route.via?.length) return [key, route]
    const [sourceMoved, targetMoved] = [changed.has(relation.source), changed.has(relation.target)]
    if (sourceMoved && targetMoved && shift) {
      return [key, { ...route, via: route.via.map(([x, y]) => [x + shift[0], y + shift[1]] as const) }]
    }
    const [source, target] = [elements.get(relation.source), elements.get(relation.target)]
    return [key, (sourceMoved || targetMoved) && source && target ? reattached(route, source, target) : route]
  }))
}

/** *arrangement* with the shape *alias* moved by (dx, dy): a box carries everything it holds. */
export const moved = (
  geometry: LayoutGeometry, arrangement: Arrangement, alias: string, dx: number, dy: number,
): Arrangement => movedTogether(geometry, arrangement, [alias], dx, dy)

/** *arrangement* with each element of *corners* moved so its top-left corner is there, carrying what it holds. */
export const placedAt = (
  geometry: LayoutGeometry, arrangement: Arrangement, corners: ReadonlyMap<string, Point>,
): Arrangement => [...corners].reduce((now, [alias, to]) => {
  const from = arrangement.elements.get(alias)
  return from ? moved(geometry, now, alias, to.x - from.left, to.y - from.top) : now
}, arrangement)

/** *arrangement* with the shape *alias* given *extent*: an element's own size, a box's stated size. */
export const resized = (
  geometry: LayoutGeometry, arrangement: Arrangement, alias: string, extent: Extent,
): Arrangement => {
  if (geometry.boxes.some((box) => box.alias === alias)) {
    return { ...arrangement, stated: new Map([...arrangement.stated, [alias, extent]]) }
  }
  const elements = new Map([...arrangement.elements, [alias, extent]])
  const routes = routesFollowing(geometry, arrangement.routes, elements, new Set([alias]), null)
  return { ...arrangement, elements, routes }
}

export type Handle = 'n' | 's' | 'e' | 'w' | 'ne' | 'nw' | 'se' | 'sw'

export const HANDLES: readonly Handle[] = ['nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w']

/** *start* with the edges *handle* names dragged by (dx, dy), never smaller than *least* either way. */
export const resizedExtent = (start: Extent, handle: Handle, dx: number, dy: number, least: number): Extent => {
  const left = handle.includes('w') ? Math.min(start.left + dx, start.right - least) : start.left
  const right = handle.includes('e') ? Math.max(start.right + dx, start.left + least) : start.right
  const top = handle.includes('n') ? Math.min(start.top + dy, start.bottom - least) : start.top
  const bottom = handle.includes('s') ? Math.max(start.bottom + dy, start.top + least) : start.bottom
  return { left, top, right, bottom }
}

