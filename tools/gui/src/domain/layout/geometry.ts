/**
 * Points and extents in a picture's own coordinates: x to the right, y downwards.
 *
 * The TypeScript mirror of `src/domain/diagrams/layout/geometry.py`, as far as the layout rules the
 * canvas applies while something is dragged need it. Extents throughout, not outlines: a shape with
 * cut or rounded corners is reasoned about by the rectangle it occupies, which is why every question
 * about being inside takes a margin.
 */

export interface Point {
  readonly x: number
  readonly y: number
}

/** The rectangle a shape occupies. */
export interface Extent {
  readonly left: number
  readonly top: number
  readonly right: number
  readonly bottom: number
}

export const widthOf = (extent: Extent): number => extent.right - extent.left

export const heightOf = (extent: Extent): number => extent.bottom - extent.top

export const centreOf = (extent: Extent): Point => ({
  x: (extent.left + extent.right) / 2,
  y: (extent.top + extent.bottom) / 2,
})

export const distanceBetween = (from: Point, to: Point): number =>
  Math.hypot(to.x - from.x, to.y - from.y)

/** How long a course is, walked point to point. */
export const courseLength = (course: readonly Point[]): number =>
  course.slice(1).reduce((walked, point, index) => walked + distanceBetween(course[index], point), 0)

/** The smallest extent holding every one of *extents*; none is an error, as `Math.min` of nothing is. */
export const unionOf = (extents: readonly Extent[]): Extent => ({
  left: Math.min(...extents.map((extent) => extent.left)),
  top: Math.min(...extents.map((extent) => extent.top)),
  right: Math.max(...extents.map((extent) => extent.right)),
  bottom: Math.max(...extents.map((extent) => extent.bottom)),
})

/** The smallest extent holding every one of *points*, or null for none (`Extent.around`). */
export const extentAround = (points: readonly Point[]): Extent | null =>
  points.length === 0 ? null
    : unionOf(points.map((point) => ({ left: point.x, top: point.y, right: point.x, bottom: point.y })))

/** *extent* with *margin* taken off every side, or null where nothing is left. */
export const shrunkBy = (extent: Extent, margin: number): Extent | null => {
  const inner = {
    left: extent.left + margin,
    top: extent.top + margin,
    right: extent.right - margin,
    bottom: extent.bottom - margin,
  }
  return widthOf(inner) > 0 && heightOf(inner) > 0 ? inner : null
}

/** Whether two extents share some area: touching along a side or at a corner is not overlapping. */
export const overlaps = (one: Extent, other: Extent): boolean =>
  one.left < other.right && other.left < one.right && one.top < other.bottom && other.top < one.bottom

/** Whether *inner* lies wholly inside *outer*. */
export const encloses = (outer: Extent, inner: Extent): boolean =>
  outer.left <= inner.left &&
  outer.top <= inner.top &&
  inner.right <= outer.right &&
  inner.bottom <= outer.bottom

/**
 * Whether the straight segment from *start* to *end* has any point inside *extent*.
 *
 * Liang–Barsky clipping: the segment is cut down against each side in turn, and it enters the
 * extent exactly when something of it survives all four.
 */
export const isEnteredBy = (extent: Extent, start: Point, end: Point): boolean => {
  const dx = end.x - start.x
  const dy = end.y - start.y
  let entering = 0
  let leaving = 1
  const sides: readonly (readonly [number, number])[] = [
    [-dx, start.x - extent.left],
    [dx, extent.right - start.x],
    [-dy, start.y - extent.top],
    [dy, extent.bottom - start.y],
  ]
  for (const [direction, distance] of sides) {
    if (direction === 0) {
      if (distance < 0) return false
      continue
    }
    const reach = distance / direction
    if (direction < 0) entering = Math.max(entering, reach)
    else leaving = Math.min(leaving, reach)
    if (entering > leaving) return false
  }
  return true
}
