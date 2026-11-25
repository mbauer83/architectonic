/**
 * What PlantUML draws round a diagram — its title, its legend — carried along as the diagram is
 * arranged, so edit mode keeps showing them where a reader sees them (owner, 2026-11-25).
 *
 * The rule is the composer's (`src/infrastructure/rendering/layout/composer.py`, `_carried_with`): a part
 * keeps to the side or the middle of the diagram it was drawn at — beside it on the left or right, else
 * centred across it; below it, else above it. The diagram is what its shapes and lines occupy, PlantUML's
 * then and the arrangement's now, read the same way both times so a picture not yet moved moves nothing.
 */
import type { Extent, Point } from '../geometry'
import { extentAround, unionOf } from '../geometry'
import type { SurroundPart } from '../../schemas/diagramLayoutGeometry'

/** What a diagram's shapes and lines occupy; null where it draws nothing. */
export const occupiedBy = (shapes: readonly Extent[], lines: readonly (readonly Point[])[]): Extent | null => {
  const around = extentAround(lines.flat())
  const all = [...shapes, ...(around ? [around] : [])]
  return all.length > 0 ? unionOf(all) : null
}

const middle = (low: number, high: number): number => (low + high) / 2

/** How a part drawn at *part* moves as the diagram goes from *was* to *now*. */
export const carriedBy = (part: Extent, was: Extent, now: Extent): Point => {
  const across = middle(part.left, part.right)
  const x = across < was.left ? now.left - was.left
    : across > was.right ? now.right - was.right
      : middle(now.left, now.right) - middle(was.left, was.right)
  const y = middle(part.top, part.bottom) > was.bottom ? now.bottom - was.bottom : now.top - was.top
  return { x, y }
}

/** A part drawn round the diagram, and how far it is carried from where PlantUML drew it. */
export interface CarriedPart {
  readonly part: SurroundPart
  readonly by: Point
  readonly extent: Extent
}

/** Each part of *surround*, carried from the diagram PlantUML drew (*was*) to the one arranged now. */
export const carriedSurround = (
  surround: readonly SurroundPart[], was: Extent | null, now: Extent | null,
): CarriedPart[] => surround.map((part) => {
  const by = was && now ? carriedBy(part.extent, was, now) : { x: 0, y: 0 }
  const { left, top, right, bottom } = part.extent
  return { part, by, extent: { left: left + by.x, top: top + by.y, right: right + by.x, bottom: bottom + by.y } }
})
