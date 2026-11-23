/**
 * What a selection rectangle chooses, and which of a selection the arranging commands act on.
 *
 * A rectangle selects the elements it encloses — or, by preference, those it touches — and only the
 * boxes it wholly encloses: a box it merely touches is the ground it was drawn on, not something chosen
 * (sketch 02·8). Align and distribute act on elements only, as the server's intents do; a box moves
 * with its members.
 */
import type { Extent } from '../geometry'
import { encloses, overlaps } from '../geometry'
import type { AlignEdge, DistributeAxis } from '../layoutIntents'
import { LEAST_TO_ALIGN, LEAST_TO_DISTRIBUTE, aligned, distributed } from '../layoutIntents'
import type { LayoutGeometry } from '../../schemas/diagramLayoutGeometry'
import type { Arrangement } from './labArrangement'
import { placedAt } from './labArrangement'
import type { Placement } from './labRouting'

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
