/**
 * Where a link meets a note, the curve between the two, and where to put a marker on it.
 *
 * Geometry rather than rendering, so it lives beside the canvas rather than in it — the component
 * was at the file-size limit and this is the honest seam: what a link *is* on screen, apart from
 * the element that carries it.
 *
 * Links attach at the **middle of a side**, chosen by which axis the two notes are further apart
 * on. Centre-to-centre was simpler and wrong: the line disappeared under the note it pointed at,
 * so an arrowhead — the thing the ontology's notation is *for* — was drawn where nobody could see
 * it.
 */

export interface NoteBox {
  readonly width: number
  readonly height: number
}

export type Point = { x: number; y: number }

/** Which side of a note a link leaves or enters by, and the point on it. */
export function anchor(from: Point, to: Point, box: NoteBox): Point {
  const a = { x: from.x + box.width / 2, y: from.y + box.height / 2 }
  const b = { x: to.x + box.width / 2, y: to.y + box.height / 2 }
  const dx = b.x - a.x
  const dy = b.y - a.y
  if (Math.abs(dx) >= Math.abs(dy)) {
    return { x: a.x + Math.sign(dx || 1) * (box.width / 2), y: a.y }
  }
  return { x: a.x, y: a.y + Math.sign(dy || 1) * (box.height / 2) }
}

/**
 * A cubic Bézier between the two anchors.
 *
 * Curved rather than straight, deliberately: a straight line reads as a decided relation, and every
 * link here is provisional until it is typed. The control points leave along the side's own axis,
 * so a curve departs perpendicular to the edge it starts on and the marker sits square to it.
 */
export function linkPath(from: Point, to: Point, box: NoteBox): string {
  const a = anchor(from, to, box)
  const b = anchor(to, from, box)
  const horizontal = Math.abs(b.x - a.x) >= Math.abs(b.y - a.y)
  const bend = Math.max(30, (horizontal ? Math.abs(b.x - a.x) : Math.abs(b.y - a.y)) * 0.4)
  const [c1, c2] = horizontal
    ? [{ x: a.x + Math.sign(b.x - a.x || 1) * bend, y: a.y },
       { x: b.x - Math.sign(b.x - a.x || 1) * bend, y: b.y }]
    : [{ x: a.x, y: a.y + Math.sign(b.y - a.y || 1) * bend },
       { x: b.x, y: b.y - Math.sign(b.y - a.y || 1) * bend }]
  return `M${a.x},${a.y} C${c1.x},${c1.y} ${c2.x},${c2.y} ${b.x},${b.y}`
}

/** Near enough to the curve's midpoint for a marker or a hit target. */
export function linkMidpoint(from: Point, to: Point, box: NoteBox): Point {
  const a = anchor(from, to, box)
  const b = anchor(to, from, box)
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 - 6 }
}
