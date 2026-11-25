/**
 * Which of a picture's shapes is in front of which (sketch 02·7, D6): painting follows containment — a
 * box and everything in it are one unit — and among the shapes directly in one box, or on the canvas,
 * the stated stacking orders them; ties keep the order PlantUML drew them in. It is the composer's
 * rule (`src/infrastructure/rendering/layout/arrangement.py`, `paint_order`), so the picture saved is
 * stacked as the picture seen.
 *
 * *Bring to front* and *Send to back* put a shape before or after all its siblings; *Bring forward* and
 * *Send backward* step it past the next sibling it overlaps, as a shape it does not touch is neither in
 * front of nor behind it in any way one can see. A restacked group of siblings is numbered afresh from
 * 0, so the layout states their whole order and nothing else.
 */
import type { Extent } from './geometry'
import { overlaps } from './geometry'
import type { Arrangement } from './lab/labArrangement'
import { childrenOf } from './lab/labArrangement'
import type { Placement } from './lab/labRouting'
import type { LayoutGeometry } from '../schemas/diagramLayoutGeometry'

export type Restack = 'front' | 'forward' | 'backward' | 'back'

/** *siblings* back to front: by stated stacking, ties as drawn. */
export const stackedSiblings = (
  siblings: readonly string[], z: ReadonlyMap<string, number> | undefined,
): readonly string[] =>
  z === undefined || z.size === 0 ? siblings
    : siblings.map((alias, at) => [alias, z.get(alias) ?? 0, at] as const)
      .sort((one, other) => one[1] - other[1] || one[2] - other[2]).map(([alias]) => alias)

const extentIn = (placement: Placement, alias: string): Extent | undefined =>
  placement.elements.get(alias) ?? placement.boxes.get(alias)

/** *order* with *alias* moved as *how* says, past the next sibling it overlaps for a step. */
const restackedOrder = (
  order: readonly string[], alias: string, how: Restack, placement: Placement,
): readonly string[] => {
  const others = order.filter((one) => one !== alias)
  if (how === 'front') return [...others, alias]
  if (how === 'back') return [alias, ...others]
  const at = order.indexOf(alias)
  const own = extentIn(placement, alias)
  const touches = (one: string): boolean => {
    const extent = extentIn(placement, one)
    return own !== undefined && extent !== undefined && overlaps(own, extent)
  }
  if (how === 'forward') {
    const past = order.findIndex((one, index) => index > at && touches(one))
    if (past < 0) return order
    const target = others.indexOf(order[past])
    return [...others.slice(0, target + 1), alias, ...others.slice(target + 1)]
  }
  const before = order.slice(0, at).map((one, index) => [one, index] as const).filter(([one]) => touches(one)).at(-1)
  if (before === undefined) return order
  const target = others.indexOf(before[0])
  return [...others.slice(0, target), alias, ...others.slice(target)]
}

/**
 * *arrangement* with the shapes *aliases* restacked as *how* says among their siblings, each group of
 * siblings it touches numbered afresh; one that cannot move further leaves the arrangement as it was.
 */
export const restacked = (
  geometry: LayoutGeometry, arrangement: Arrangement, placement: Placement,
  aliases: readonly string[], how: Restack,
): Arrangement => {
  const parentOf = new Map([...geometry.boxes, ...geometry.elements].map((shape) => [shape.alias, shape.inside ?? null]))
  const children = childrenOf(geometry)
  const z = new Map(arrangement.z ?? [])
  let changed = false
  const ordered = (parent: string | null) => stackedSiblings(children.get(parent) ?? [], z)
  const place = (alias: string) => ordered(parentOf.get(alias) ?? null).indexOf(alias)
  // So a selection keeps its own order: to an end, the one nearest the other end goes first; a step
  // starts with the one nearest where it steps to, so none steps past another of the selection.
  const backFirst = how === 'front' || how === 'backward'
  const sequence = aliases.filter((alias) => parentOf.has(alias))
    .sort((a, b) => (backFirst ? place(a) - place(b) : place(b) - place(a)))
  for (const alias of sequence) {
    const before = ordered(parentOf.get(alias) ?? null)
    const after = restackedOrder(before, alias, how, placement)
    if (after.every((one, index) => one === before[index])) continue
    changed = true
    after.forEach((one, index) => z.set(one, index))
  }
  return changed ? { ...arrangement, z } : arrangement
}
