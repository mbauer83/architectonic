/**
 * Align and distribute: where each of several elements goes when they are lined up on one edge, or
 * spread with equal gaps between neighbours.
 *
 * The TypeScript mirror of `_aligned` and `_distributed` in `src/domain/diagrams/layout/layout_intents.py`,
 * held equal to it by `tests/fixtures/layout_geometry/intents.json`. A centre is the centre of the
 * selection's bounding box; distributing keeps the first and the last where they are, ordered by their
 * leading edge and then by key. Each answer is an element's new top-left corner, a half rounded up
 * (`halfUp`), the one rounding both languages share.
 */
import type { Extent, Point } from './geometry'
import { heightOf, widthOf } from './geometry'
import { halfUp } from './orthogonal'

/** The edge, or the centre line, elements are aligned on: the server's names. */
export type AlignEdge = 'left' | 'right' | 'top' | 'bottom' | 'centre_x' | 'centre_y'

/** The axis elements are distributed along. */
export type DistributeAxis = 'x' | 'y'

/** Aligning needs two elements; distributing three, since the outer two stay. */
export const LEAST_TO_ALIGN = 2
export const LEAST_TO_DISTRIBUTE = 3

const corner = (x: number, y: number): Point => ({ x: halfUp(x), y: halfUp(y) })

/** Each of *extents* lined up on *edge* of the box round them all; the other axis is kept. */
export const aligned = (extents: ReadonlyMap<string, Extent>, edge: AlignEdge): ReadonlyMap<string, Point> => {
  const all = [...extents.values()]
  const left = Math.min(...all.map((e) => e.left))
  const right = Math.max(...all.map((e) => e.right))
  const top = Math.min(...all.map((e) => e.top))
  const bottom = Math.max(...all.map((e) => e.bottom))
  const to = (e: Extent): Point => {
    switch (edge) {
      case 'left': return corner(left, e.top)
      case 'right': return corner(right - widthOf(e), e.top)
      case 'centre_x': return corner((left + right - widthOf(e)) / 2, e.top)
      case 'top': return corner(e.left, top)
      case 'bottom': return corner(e.left, bottom - heightOf(e))
      case 'centre_y': return corner(e.left, (top + bottom - heightOf(e)) / 2)
    }
  }
  return new Map([...extents].map(([key, e]) => [key, to(e)]))
}

/** *extents* spread along *axis* with equal gaps between neighbours; the first and the last stay. */
export const distributed = (
  extents: ReadonlyMap<string, Extent>, axis: DistributeAxis,
): ReadonlyMap<string, Point> => {
  const alongX = axis === 'x'
  const start = (e: Extent): number => (alongX ? e.left : e.top)
  const size = (e: Extent): number => (alongX ? widthOf(e) : heightOf(e))
  const order = [...extents].sort(([oneKey, one], [otherKey, other]) =>
    start(one) - start(other) || (oneKey < otherKey ? -1 : oneKey > otherKey ? 1 : 0))
  const first = order[0][1]
  const last = order[order.length - 1][1]
  const sizes = order.reduce((sum, [, e]) => sum + size(e), 0)
  const gap = (start(last) + size(last) - start(first) - sizes) / (order.length - 1)
  const result = new Map<string, Point>()
  let at = start(first)
  for (const [key, e] of order) {
    result.set(key, alongX ? corner(at, e.top) : corner(e.left, at))
    at += size(e) + gap
  }
  return result
}
