/**
 * The band along an element's edge that draws a relation from it (sketch 01·10, 03·8): a press within
 * a few screen pixels inside its outline starts a relation rather than a move, the cursor turns to a
 * crosshair there, and the side the pointer is nearest lights up. One reading of the band serves all
 * three, so what lights up is what a press does.
 */
import type { Extent, Point } from './geometry'

export type Side = 'left' | 'right' | 'top' | 'bottom'

/** How deep the band reaches inside an element's outline, in screen pixels. */
export const EDGE_BAND = 5

/** The side of *extent* whose band holds *at*; null when *at* is deeper inside, or outside. */
export const sideInBand = (extent: Extent, at: Point, band = EDGE_BAND): Side | null => {
  const depth: Readonly<Record<Side, number>> = {
    left: at.x - extent.left, right: extent.right - at.x, top: at.y - extent.top, bottom: extent.bottom - at.y,
  }
  const sides = Object.keys(depth) as Side[]
  if (sides.some((side) => depth[side] < 0)) return null
  const nearest = sides.reduce((one, other) => (depth[other] < depth[one] ? other : one))
  return depth[nearest] < band ? nearest : null
}

/** The stretch of *extent*'s outline along *side*, as two points. */
export const sideOf = (extent: Extent, side: Side): readonly [Point, Point] => {
  switch (side) {
    case 'left': return [{ x: extent.left, y: extent.top }, { x: extent.left, y: extent.bottom }]
    case 'right': return [{ x: extent.right, y: extent.top }, { x: extent.right, y: extent.bottom }]
    case 'top': return [{ x: extent.left, y: extent.top }, { x: extent.right, y: extent.top }]
    case 'bottom': return [{ x: extent.left, y: extent.bottom }, { x: extent.right, y: extent.bottom }]
  }
}
