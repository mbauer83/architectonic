/**
 * The one order the lab paints its picture in, back to front: shapes by nesting — a box, then
 * everything it holds — then the lines, then their labels. The backdrop is behind all of it and the
 * lab's own marks (breaches, handles) in front; neither is part of this order.
 *
 * Two things move a shape out of the order PlantUML drew it in:
 *
 * - **Lifting.** The shape last pressed, with everything it holds and every box holding it, is painted
 *   after its siblings, so what is being dragged is brought into view and stays there once dropped. A
 *   box is still painted before its contents: lifting never reorders a nesting.
 * - **Widening.** A shape resized by its own handles is painted after the siblings it does not overlap
 *   but *before* the ones it does, so a widened box never covers a sibling's content. The boxes
 *   holding it are lifted as for a move: resizing what a box holds never sends the box behind a
 *   sibling it was already in front of.
 *
 * A line is painted in the top layer, over every shape, as the composed picture draws it — unless a
 * shape painted after one of its ends covers that end. Then the line is painted just before that
 * shape, so whatever hides an element hides the lines into it too, and a line is never left lying on
 * top of a box with its element out of sight underneath. That holds whatever the hiding shape is: a
 * box holding the line's other end, or the other end itself. Only a shape the end itself holds does
 * not hide it. A line crossing a box that hides neither end stays on top.
 */
import type { Extent } from '../../../domain/layout/geometry'
import { overlaps } from '../../../domain/layout/geometry'
import { childrenOf, descendantsOf } from '../../../domain/layout/lab/labArrangement'
import type { LabGeometry } from '../../../domain/layout/lab/labGeometry'
import type { Placement } from '../../../domain/layout/lab/labRouting'

/** The shape last pressed, and whether the press moved it or resized it. */
export interface Lift {
  readonly alias: string
  readonly how: 'moved' | 'resized'
}

export type Painted =
  | { readonly kind: 'shape'; readonly alias: string; readonly isBox: boolean }
  | { readonly kind: 'line'; readonly relation: number }
  | { readonly kind: 'label'; readonly relation: number }

type PaintedShape = Extract<Painted, { kind: 'shape' }>

const extentIn = (placement: Placement, alias: string): Extent | undefined =>
  placement.elements.get(alias) ?? placement.boxes.get(alias)

/** *lifted* and every box holding it. */
const liftedChain = (geometry: LabGeometry, lifted: string): ReadonlySet<string> => {
  const inside = new Map([...geometry.boxes, ...geometry.elements].map((shape) => [shape.alias, shape.inside]))
  const chain = new Set<string>()
  for (let alias: string | null = lifted; alias !== null && !chain.has(alias); alias = inside.get(alias) ?? null) {
    chain.add(alias)
  }
  return chain
}

/** *siblings* with the one in *chain* moved in front of those it may cover. */
const siblingsInOrder = (
  siblings: readonly string[], chain: ReadonlySet<string>, lift: Lift, placement: Placement,
): readonly string[] => {
  const lifted = siblings.find((alias) => chain.has(alias))
  if (lifted === undefined) return siblings
  const others = siblings.filter((alias) => alias !== lifted)
  if (lift.how === 'moved' || lifted !== lift.alias) return [...others, lifted]
  const widened = extentIn(placement, lifted)
  const covered = (alias: string): boolean => {
    const sibling = extentIn(placement, alias)
    return widened !== undefined && sibling !== undefined && overlaps(widened, sibling)
  }
  return [...others.filter((alias) => !covered(alias)), lifted, ...others.filter(covered)]
}

/** Every shape back to front: a box, then everything in it; siblings as drawn, save the lifted one. */
export const shapeOrder = (geometry: LabGeometry, placement: Placement, lift: Lift | null): PaintedShape[] => {
  const boxes = new Set(geometry.boxes.map((box) => box.alias))
  const children = childrenOf(geometry)
  const chain = lift ? liftedChain(geometry, lift.alias) : new Set<string>()
  const walk = (parent: string | null): PaintedShape[] => {
    const siblings = children.get(parent) ?? []
    const ordered = lift ? siblingsInOrder(siblings, chain, lift, placement) : siblings
    return ordered.flatMap((alias) => [{ kind: 'shape' as const, alias, isBox: boxes.has(alias) }, ...walk(alias)])
  }
  return walk(null)
}

/**
 * Where in *shapes* each line is sunk: the place of the first shape painted after one of its ends that
 * covers that end — any shape but one the end holds. A line no shape hides is absent.
 */
const sunkLines = (geometry: LabGeometry, placement: Placement, shapes: readonly PaintedShape[]): Map<number, number> => {
  const place = new Map(shapes.map((shape, index) => [shape.alias, index]))
  const held = new Map<string, ReadonlySet<string>>()
  const heldBy = (alias: string): ReadonlySet<string> => {
    const known = held.get(alias) ?? new Set(descendantsOf(geometry, alias))
    held.set(alias, known)
    return known
  }
  const hiderOf = (end: string): number | null => {
    const from = place.get(end)
    const extent = extentIn(placement, end)
    if (from === undefined || extent === undefined) return null
    const hider = shapes.findIndex((shape, index) => {
      const over = extentIn(placement, shape.alias)
      return index > from && !heldBy(end).has(shape.alias) && over !== undefined && overlaps(over, extent)
    })
    return hider < 0 ? null : hider
  }
  return new Map(geometry.relations.flatMap((relation): [number, number][] => {
    const hiders = [relation.source, relation.target].map(hiderOf).filter((at): at is number => at !== null)
    return hiders.length > 0 ? [[relation.index, Math.min(...hiders)]] : []
  }))
}

/** The whole picture back to front: shapes, each hidden line just below what hides it, then the rest. */
export const paintOrder = (geometry: LabGeometry, placement: Placement, lift: Lift | null): Painted[] => {
  const shapes = shapeOrder(geometry, placement, lift)
  const sunk = sunkLines(geometry, placement, shapes)
  const lineAndLabel = (relation: number): Painted[] =>
    [{ kind: 'line', relation }, { kind: 'label', relation }]
  const sunkAt = (index: number): Painted[] =>
    geometry.relations.filter((relation) => sunk.get(relation.index) === index)
      .flatMap((relation) => lineAndLabel(relation.index))
  const onTop = geometry.relations.filter((relation) => !sunk.has(relation.index))
  return [
    ...shapes.flatMap((shape, index): Painted[] => [...sunkAt(index), shape]),
    ...onTop.map((relation): Painted => ({ kind: 'line', relation: relation.index })),
    ...onTop.map((relation): Painted => ({ kind: 'label', relation: relation.index })),
  ]
}
