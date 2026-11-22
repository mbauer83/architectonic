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
import type { Extent } from '../geometry'
import { widthOf } from '../geometry'
import type { GeometryBox, LayoutGeometry, MeasuredWord } from '../../schemas/diagramLayoutGeometry'

/** What has been moved or resized: every element where it is now, and each box stated by size. */
export interface Arrangement {
  readonly elements: ReadonlyMap<string, Extent>
  readonly stated: ReadonlyMap<string, Extent>
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

export const unionOf = (extents: readonly Extent[]): Extent => ({
  left: Math.min(...extents.map((extent) => extent.left)),
  top: Math.min(...extents.map((extent) => extent.top)),
  right: Math.max(...extents.map((extent) => extent.right)),
  bottom: Math.max(...extents.map((extent) => extent.bottom)),
})

/** PlantUML's arrangement: every element where it drew it, nothing stated. */
export const drawnArrangement = (geometry: LayoutGeometry): Arrangement => ({
  elements: new Map(geometry.elements.map((element) => [element.alias, element.extent])),
  stated: new Map(),
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

/** *arrangement* with the shape *alias* moved by (dx, dy): a box carries everything it holds. */
export const moved = (
  geometry: LayoutGeometry, arrangement: Arrangement, alias: string, dx: number, dy: number,
): Arrangement => {
  const carried = new Set([alias, ...descendantsOf(geometry, alias)])
  const shift = (entries: ReadonlyMap<string, Extent>): Map<string, Extent> =>
    new Map([...entries].map(([key, extent]) => [key, carried.has(key) ? translated(extent, dx, dy) : extent]))
  return { elements: shift(arrangement.elements), stated: shift(arrangement.stated) }
}

/** *arrangement* with the shape *alias* given *extent*: an element's own size, a box's stated size. */
export const resized = (
  geometry: LayoutGeometry, arrangement: Arrangement, alias: string, extent: Extent,
): Arrangement =>
  geometry.boxes.some((box) => box.alias === alias)
    ? { ...arrangement, stated: new Map([...arrangement.stated, [alias, extent]]) }
    : { ...arrangement, elements: new Map([...arrangement.elements, [alias, extent]]) }

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

