/**
 * An arrangement and the layout block a diagram states for it, both ways, and what an edit changed.
 *
 * - `arrangedBy` reads a stored block onto PlantUML's picture: each element at its corner, at its
 *   stated size or the one PlantUML drew; each box at its stated extent. Positions a block does not
 *   state stay where PlantUML put them, as the composer leaves them.
 * - `layoutOf` writes an arrangement down whole, as a first layout is (`first_layout.py`): every
 *   element at its corner, sized only where resized; every box the layout can name at its extent.
 * - `layoutPatchBetween` is the patch that turns the stored block into another one, each entry
 *   checked against what was read, so a layout changed meanwhile is refused rather than overwritten.
 * - `arrangedUnits` counts what an edit arranged: a box moved with its contents is one change, not
 *   one per member, and a box that only grew around a moved member is not a change of its own.
 */
import type { Extent } from './geometry'
import { heightOf, widthOf } from './geometry'
import type { LayoutGeometry } from '../schemas/diagramLayoutGeometry'
import type { Arrangement } from './lab/labArrangement'
import { drawnArrangement } from './lab/labArrangement'
import { placementOf } from './lab/labRouting'

/** A shape's place as a layout block states it: its corner, and its size where it states one. */
export interface Placed {
  readonly x: number
  readonly y: number
  readonly w?: number
  readonly h?: number
}

/** The two sections of a layout block an arrangement states. */
export interface ArrangedLayout {
  readonly elements: Readonly<Record<string, Placed>>
  readonly boxes: Readonly<Record<string, Placed>>
}

/** The sections a stored block may hold that an arrangement reads and writes. */
export interface StoredLayout {
  readonly elements?: Readonly<Record<string, Placed>>
  readonly boxes?: Readonly<Record<string, Placed>>
}

const SAME = 0.5

const extentAt = (placed: Placed, drawn: Extent): Extent => ({
  left: placed.x,
  top: placed.y,
  right: placed.x + (placed.w ?? widthOf(drawn)),
  bottom: placed.y + (placed.h ?? heightOf(drawn)),
})

/** The arrangement *stored* states over PlantUML's picture *geometry*. */
export const arrangedBy = (geometry: LayoutGeometry, stored: StoredLayout): Arrangement => {
  const drawn = drawnArrangement(geometry)
  const elementsStated = stored.elements ?? {}
  const boxesStated = stored.boxes ?? {}
  const elements = new Map([...drawn.elements].map(([alias, extent]) => {
    const key = geometry.elements.find((one) => one.alias === alias)?.key
    const placed = key === undefined ? undefined : elementsStated[key]
    return [alias, placed ? extentAt(placed, extent) : extent] as const
  }))
  const stated = new Map(geometry.boxes.flatMap((box): [string, Extent][] => {
    const placed = box.key === undefined ? undefined
      : (box.section === 'elements' ? elementsStated : boxesStated)[box.key]
    return placed ? [[box.alias, extentAt(placed, box.extent)]] : []
  }))
  return { elements, stated }
}

const placedAt = (extent: Extent, sized: boolean): Placed => ({
  x: Math.round(extent.left),
  y: Math.round(extent.top),
  ...(sized ? { w: Math.max(1, Math.round(widthOf(extent))), h: Math.max(1, Math.round(heightOf(extent))) } : {}),
})

const resized = (now: Extent, drawn: Extent): boolean =>
  Math.abs(widthOf(now) - widthOf(drawn)) > SAME || Math.abs(heightOf(now) - heightOf(drawn)) > SAME

/** *arrangement* written down whole, every shape by the key the layout names it by. */
export const layoutOf = (geometry: LayoutGeometry, arrangement: Arrangement): ArrangedLayout => {
  const placement = placementOf(geometry, arrangement)
  const elements: Record<string, Placed> = {}
  const boxes: Record<string, Placed> = {}
  for (const element of geometry.elements) {
    const now = placement.elements.get(element.alias)
    if (element.key !== undefined && now) elements[element.key] = placedAt(now, resized(now, element.extent))
  }
  for (const box of geometry.boxes) {
    const now = placement.boxes.get(box.alias)
    if (box.key !== undefined && now) (box.section === 'elements' ? elements : boxes)[box.key] = placedAt(now, true)
  }
  return { elements, boxes }
}

/** One entry of a layout patch: what it becomes (null removes it) and what it was read as. */
export interface EntryChange {
  readonly value: Placed | null
  readonly based_on: Placed | null
}

export type ArrangementPatch = Readonly<Record<'elements' | 'boxes', Readonly<Record<string, EntryChange>>>>

const samePlaced = (one: Placed | undefined, other: Placed | undefined): boolean =>
  one?.x === other?.x && one?.y === other?.y && one?.w === other?.w && one?.h === other?.h

const sectionPatch = (
  stored: Readonly<Record<string, Placed>>, wanted: Readonly<Record<string, Placed>>,
): Record<string, EntryChange> =>
  Object.fromEntries([...new Set([...Object.keys(stored), ...Object.keys(wanted)])].flatMap((key) =>
    samePlaced(stored[key], wanted[key]) ? []
      : [[key, { value: wanted[key] ?? null, based_on: stored[key] ?? null }]]))

/** The patch turning *stored* into *wanted*; null for *wanted* removes every entry *stored* holds. */
export const layoutPatchBetween = (stored: StoredLayout, wanted: ArrangedLayout | null): ArrangementPatch => ({
  elements: sectionPatch(stored.elements ?? {}, wanted?.elements ?? {}),
  boxes: sectionPatch(stored.boxes ?? {}, wanted?.boxes ?? {}),
})

export const patchIsEmpty = (patch: ArrangementPatch): boolean =>
  Object.keys(patch.elements).length === 0 && Object.keys(patch.boxes).length === 0

const sameExtent = (one: Extent | undefined, other: Extent | undefined): boolean =>
  one !== undefined && other !== undefined && Math.abs(one.left - other.left) <= SAME
  && Math.abs(one.top - other.top) <= SAME && !resized(one, other)

const shiftOf = (from: Extent, to: Extent): readonly [number, number] => [to.left - from.left, to.top - from.top]

/**
 * The shapes an edit arranged from *before* to *after*, by alias: an element moved or resized, a box
 * stated anew. A shape carried by a box that moved by the same amount is the box's change, not its own.
 */
export const arrangedUnits = (
  geometry: LayoutGeometry, before: Arrangement, after: Arrangement,
): readonly string[] => {
  const inside = new Map([...geometry.boxes, ...geometry.elements].map((shape) => [shape.alias, shape.inside]))
  const was = placementOf(geometry, before)
  const now = placementOf(geometry, after)
  const extentIn = (placement: typeof was, alias: string): Extent | undefined =>
    placement.elements.get(alias) ?? placement.boxes.get(alias)
  const changed = (alias: string): boolean => {
    const box = geometry.boxes.some((one) => one.alias === alias)
    const [from, to] = [extentIn(was, alias), extentIn(now, alias)]
    if (!box) return !sameExtent(from, to)
    const statedAnew = (before.stated.has(alias) || after.stated.has(alias))
      && !sameExtent(before.stated.get(alias), after.stated.get(alias))
    // Moved whole, contents and all; a box that only grew round a moved member is not arranged.
    const movedWhole = from !== undefined && to !== undefined && !resized(from, to) && !sameExtent(from, to)
    return statedAnew || movedWhole
  }
  const carried = (alias: string): boolean => {
    const parent = inside.get(alias)
    const [from, to, parentFrom, parentTo] = [
      extentIn(was, alias), extentIn(now, alias),
      parent === undefined ? undefined : extentIn(was, parent),
      parent === undefined ? undefined : extentIn(now, parent),
    ]
    if (!parent || !from || !to || !parentFrom || !parentTo || !changed(parent)) return false
    const [dx, dy] = shiftOf(from, to)
    const [px, py] = shiftOf(parentFrom, parentTo)
    return Math.abs(dx - px) <= SAME && Math.abs(dy - py) <= SAME
  }
  return [...inside.keys()].filter((alias) => changed(alias) && !carried(alias))
}
