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
 *   one per member, and a box that only grew around a moved member is not a change of its own;
 *   `shapedLines` names each line whose stated route an edit changed.
 *
 * A relation's route is written as the block spells it (`Route`): only what was stated, by relation key.
 */
import type { Extent } from './geometry'
import { heightOf, widthOf } from './geometry'
import type { DiagramLayoutSchema } from '../schemas/diagramLayout'
import type { LayoutGeometry } from '../schemas/diagramLayoutGeometry'
import type { Route } from './orthogonal'
import type { Arrangement } from './lab/labArrangement'
import { drawnArrangement } from './lab/labArrangement'
import { placementOf } from './lab/labRouting'
import { statedWhole } from './lab/labRouteEdits'
import type { RoutedConnector } from './routing/scene'

/** *geometry* less the elements *removed* names, by alias, and every line into them. */
export const withoutElements = (geometry: LayoutGeometry, removed: ReadonlySet<string>): LayoutGeometry =>
  removed.size === 0 ? geometry : {
    ...geometry,
    elements: geometry.elements.filter((one) => !removed.has(one.alias)),
    relations: geometry.relations.filter((one) => !removed.has(one.source) && !removed.has(one.target)),
  }

/** A shape's place as a layout block states it: its corner, and its size where it states one. */
export interface Placed {
  readonly x: number
  readonly y: number
  readonly w?: number
  readonly h?: number
}

/** The sections of a layout block an arrangement states. */
export interface ArrangedLayout {
  readonly elements: Readonly<Record<string, Placed>>
  readonly boxes: Readonly<Record<string, Placed>>
  readonly relations?: Readonly<Record<string, Route>>
  /** The stacking, by the key that names the shape in `elements` or `boxes`. */
  readonly z?: Readonly<Record<string, number>>
}

/** The sections of a stored block an arrangement reads and writes: the layout contract's own. */
export type StoredLayout = Pick<typeof DiagramLayoutSchema.Type, 'elements' | 'boxes' | 'relations' | 'z'>

/** Every shape's alias by the key a layout names it by; a shape the layout cannot name is absent. */
const aliasesByKey = (geometry: LayoutGeometry): ReadonlyMap<string, string> =>
  new Map([...geometry.elements, ...geometry.boxes].flatMap((shape) =>
    (shape.key === undefined ? [] : [[shape.key, shape.alias] as const])))

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
  const drawnKeys = new Set(geometry.relations.flatMap((one) => (one.key === undefined ? [] : [one.key])))
  const routes = new Map(Object.entries(stored.relations ?? {}).filter(([key]) => drawnKeys.has(key)))
  const aliases = aliasesByKey(geometry)
  const z = new Map(Object.entries(stored.z ?? {}).flatMap(([key, value]): [string, number][] => {
    const alias = aliases.get(key)
    return alias === undefined ? [] : [[alias, value]]
  }))
  return { elements, stated, routes, ...(z.size ? { z } : {}) }
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
  const keys = new Map([...aliasesByKey(geometry)].map(([key, alias]) => [alias, key]))
  const z = Object.fromEntries([...arrangement.z ?? []].flatMap(([alias, value]): [string, number][] => {
    const key = keys.get(alias)
    return key === undefined ? [] : [[key, value]]
  }))
  return { elements, boxes, relations: Object.fromEntries(arrangement.routes), ...(Object.keys(z).length ? { z } : {}) }
}

/** One entry of a layout patch: what it becomes (null removes it) and what it was read as. */
export interface EntryChange<Value = Placed> {
  readonly value: Value | null
  readonly based_on: Value | null
}

export type ArrangementPatch = {
  readonly elements: Readonly<Record<string, EntryChange>>
  readonly boxes: Readonly<Record<string, EntryChange>>
  readonly relations: Readonly<Record<string, EntryChange<Route>>>
  readonly z: Readonly<Record<string, EntryChange<number>>>
}

const samePlaced = (one: Placed | undefined, other: Placed | undefined): boolean =>
  one?.x === other?.x && one?.y === other?.y && one?.w === other?.w && one?.h === other?.h

/** Whether two routes state the same: the same parts, each the same, whatever order they were written in. */
export const sameRoute = (one: Route | undefined, other: Route | undefined): boolean => {
  const written = (route: Route | undefined) => route && JSON.stringify([route.from, route.to, route.via, route.label])
  return written(one) === written(other)
}

const sectionPatch = <Value>(
  stored: Readonly<Record<string, Value>>, wanted: Readonly<Record<string, Value>>,
  same: (one: Value | undefined, other: Value | undefined) => boolean,
): Record<string, EntryChange<Value>> =>
  Object.fromEntries([...new Set([...Object.keys(stored), ...Object.keys(wanted)])].flatMap((key) =>
    same(stored[key], wanted[key]) ? []
      : [[key, { value: wanted[key] ?? null, based_on: stored[key] ?? null }]]))

/** The patch turning *stored* into *wanted*; null for *wanted* removes every entry *stored* holds. */
export const layoutPatchBetween = (stored: StoredLayout, wanted: ArrangedLayout | null): ArrangementPatch => ({
  elements: sectionPatch(stored.elements ?? {}, wanted?.elements ?? {}, samePlaced),
  boxes: sectionPatch(stored.boxes ?? {}, wanted?.boxes ?? {}, samePlaced),
  relations: sectionPatch<Route>(stored.relations ?? {}, wanted?.relations ?? {}, sameRoute),
  z: sectionPatch<number>(stored.z ?? {}, wanted?.z ?? {}, (one, other) => one === other),
})

export const patchIsEmpty = (patch: ArrangementPatch): boolean =>
  [patch.elements, patch.boxes, patch.relations, patch.z].every((section) => Object.keys(section).length === 0)

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
  const restacked = (alias: string): boolean => (before.z?.get(alias) ?? 0) !== (after.z?.get(alias) ?? 0)
  return [...inside.keys()].filter((alias) => (changed(alias) && !carried(alias)) || restacked(alias))
}

/** The lines whose stated route an edit changed from *before* to *after*, by their place on the picture. */
export const shapedLines = (geometry: LayoutGeometry, before: Arrangement, after: Arrangement): readonly number[] =>
  geometry.relations.filter((relation) => relation.key !== undefined
    && !sameRoute(before.routes.get(relation.key), after.routes.get(relation.key))).map((relation) => relation.index)

/**
 * The lines an edit arranged of themselves (sketch 01·6): stated anew from *before* to *after* while
 * neither end was placed elsewhere. A line that follows an end moved, or carried by its box, is part of
 * that end's arranging and no change of its own.
 */
export const linesArranged = (geometry: LayoutGeometry, before: Arrangement, after: Arrangement): readonly number[] => {
  const [was, now] = [placementOf(geometry, before), placementOf(geometry, after)]
  const stayed = (alias: string): boolean => sameExtent(
    was.elements.get(alias) ?? was.boxes.get(alias), now.elements.get(alias) ?? now.boxes.get(alias))
  const ends = new Map(geometry.relations.map((relation) => [relation.index, [relation.source, relation.target]]))
  return shapedLines(geometry, before, after).filter((index) => (ends.get(index) ?? []).every(stayed))
}

/**
 * What Save states for the lines the session moved (owner, 2026-11-24): each line with an end on an
 * element now placed elsewhere than in *reference* is written as the course the editor showed, so a
 * saved diagram keeps the lines that were seen. Lines nothing moved stay the router's, and a route the
 * user stated by hand (*stated*) is kept as stated.
 */
export const shownRoutesOfMoved = (
  geometry: LayoutGeometry, reference: Arrangement, now: Arrangement,
  routed: ReadonlyMap<string, RoutedConnector>,
): Record<string, Route> => {
  const moved = (alias: string) => !sameExtent(reference.elements.get(alias), now.elements.get(alias))
  return Object.fromEntries(geometry.relations.flatMap((relation): [string, Route][] => {
    const connector = routed.get(String(relation.index))
    if (relation.key === undefined || now.routes.has(relation.key) || connector === undefined) return []
    return moved(relation.source) || moved(relation.target) ? [[relation.key, statedWhole(connector)]] : []
  }))
}

