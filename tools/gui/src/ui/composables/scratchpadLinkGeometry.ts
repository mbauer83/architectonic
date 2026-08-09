/**
 * The curve a link is drawn as, and where to put a marker on it.
 *
 * Geometry rather than rendering, so it lives beside the canvas rather than in it — the component
 * was at the file-size limit and this is the honest seam: what a link *is* on screen, apart from
 * the element that carries it.
 */

export interface NoteBox {
  readonly width: number
  readonly height: number
}

type Point = { x: number; y: number }

const centre = (at: Point, box: NoteBox): Point => ({
  x: at.x + box.width / 2,
  y: at.y + box.height / 2,
})

/**
 * A cubic Bézier between two notes' centres.
 *
 * Curved rather than straight, deliberately: a straight line reads as a decided relation, and every
 * link here is provisional until it is typed. The control points run horizontally so the curve
 * leaves and enters along the axis a reader scans.
 */
export function linkPath(from: Point, to: Point, box: NoteBox): string {
  const a = centre(from, box)
  const b = centre(to, box)
  const bend = Math.max(40, Math.abs(b.x - a.x) * 0.4)
  return `M${a.x},${a.y} C${a.x + bend},${a.y} ${b.x - bend},${b.y} ${b.x},${b.y}`
}

/** Near enough to the curve's midpoint for a marker: the control points are horizontal, so the
 * curve passes close to the straight-line midpoint. */
export function linkMidpoint(from: Point, to: Point, box: NoteBox): Point {
  return {
    x: (from.x + to.x) / 2 + box.width / 2,
    y: (from.y + to.y) / 2 + box.height / 2 - 6,
  }
}
