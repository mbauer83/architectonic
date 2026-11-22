/**
 * Which of PlantUML's drawings a shape is drawn with in the lab, and where.
 *
 * Everything is drawn with PlantUML's own markup, as the composer draws it. A shape at the size
 * PlantUML drew it is that drawing, shifted — what the composer's `placed_shape` does. A shape at
 * another size is the drawing the composer made of it at that size (`Reshaped`, asked of the lab's
 * backend, which answers with `fitted_box` or `resized_element`), shifted from where it was made for;
 * until that answer arrives, the last one there is — or PlantUML's own — stands in.
 */
import type { Extent } from '../geometry'
import type { DrawingNode } from '../../schemas/diagramLayoutGeometry'
import { resizedFromDrawn } from './labRouting'

/** A shape as the composer drew it at a size other than PlantUML's, and the extent it drew it for. */
export interface Reshaped {
  readonly at: Extent
  readonly drawing: DrawingNode
}

export interface PlacedDrawing {
  readonly drawing: DrawingNode
  readonly transform: string
}

const sameSize = (one: Extent, other: Extent): boolean => !resizedFromDrawn(other, one)

const shifted = (from: Extent, to: Extent): string => `translate(${to.left - from.left} ${to.top - from.top})`

/** What a shape PlantUML drew over *drawn* as *drawing* is drawn with where it is *now*. */
export const shapeDrawing = (
  drawn: Extent, drawing: DrawingNode, now: Extent, reshaped: Reshaped | undefined,
): PlacedDrawing => {
  const source = sameSize(drawn, now) || !reshaped ? { at: drawn, drawing } : reshaped
  return { drawing: source.drawing, transform: shifted(source.at, now) }
}

/** The shapes whose drawing at their size now is still to be asked for: resized, and not yet drawn so. */
export const stillToReshape = (
  drawnAt: ReadonlyMap<string, Extent>, now: ReadonlyMap<string, Extent>, reshaped: ReadonlyMap<string, Reshaped>,
): string[] =>
  [...now].flatMap(([alias, extent]) => {
    const drawn = drawnAt.get(alias)
    const made = reshaped.get(alias)
    return drawn && !sameSize(drawn, extent) && !(made && sameSize(made.at, extent)) ? [alias] : []
  })
