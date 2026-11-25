/**
 * Where a moved or resized shape lands (sketch 02·1, 02·2, 04·4; D8).
 *
 * An edge or the centre of what moves that comes within a few screen pixels of an edge or the centre of
 * a neighbour — an element or a box — lands on it, and a guide says so. Otherwise it lands on the fine
 * grid. Which lines are looked at is the gesture's: a move aligns its three lines on each axis, a resize
 * only the edge being dragged. The reader may ask for the guides as hints only (Preferences): nothing
 * then snaps, neither to a neighbour nor to the grid, and a guide still shows what lines up.
 *
 * Only neighbours within reach are looked at, so a shape never snaps to something far off-screen; and
 * never to what moves along with it, nor to a box that holds it, whose extent follows the move.
 */
import type { Extent, Point } from '../geometry'
import type { Port } from '../orthogonal'
import { leavesLevel, portPoint } from '../orthogonal'
import type { LayoutGeometry } from '../../schemas/diagramLayoutGeometry'
import type { Handle } from './labArrangement'
import { descendantsOf } from './labArrangement'
import type { Placement } from './labRouting'

/** The fine grid a shape lands on, in the picture's units. */
export const GRID = 8
/** How near, on screen, a line must come to a neighbour's to align with it. */
export const ALIGN_PIXELS = 6
/** How far off, in the picture's units, a neighbour may be and still be aligned to. */
export const NEIGHBOUR_REACH = 1500
/** How far a guide runs on past the two shapes it joins. */
const GUIDE_OVERRUN = 8

/** Whether a move or resize snaps, or only shows what lines up (Preferences). */
export type Snapping = 'snap' | 'hints'

type Axis = 'x' | 'y'
/** A line of a shape across one axis: its low edge, its centre, its high edge. */
type Line = 'low' | 'centre' | 'high'

/** A dashed guide: the line *at* across *axis* (`x`: a vertical line), drawn from *from* to *to*. */
export interface Guide {
  readonly axis: Axis
  readonly at: number
  readonly from: number
  readonly to: number
}

/** Which lines of a shape a gesture aligns, on each axis. */
export interface MovingLines {
  readonly x: readonly Line[]
  readonly y: readonly Line[]
}

/** How far to correct what a gesture reached, on each axis, and the guides that say why. */
export interface Snapped {
  readonly dx: number
  readonly dy: number
  readonly guides: readonly Guide[]
}

const ALL_LINES: readonly Line[] = ['low', 'centre', 'high']

/** A move aligns every line; a resize only the edges its handle drags. */
export const movingLinesOf = (handle: Handle | null): MovingLines => {
  if (handle === null) return { x: ALL_LINES, y: ALL_LINES }
  const dragged = (low: string, high: string): Line[] =>
    handle.includes(low) ? ['low'] : handle.includes(high) ? ['high'] : []
  return { x: dragged('w', 'e'), y: dragged('n', 's') }
}

const span = (extent: Extent, axis: Axis): readonly [number, number] =>
  (axis === 'x' ? [extent.left, extent.right] : [extent.top, extent.bottom])

const lineAt = (extent: Extent, axis: Axis, line: Line): number => {
  const [low, high] = span(extent, axis)
  return line === 'low' ? low : line === 'high' ? high : (low + high) / 2
}

interface Alignment {
  readonly distance: number
  readonly from: number
  readonly at: number
  readonly other: Extent
}

/** The nearest neighbour line within *tolerance* of one of *lines* of *extent*; null where none is. */
const alignmentOn = (
  axis: Axis, extent: Extent, lines: readonly Line[], neighbours: readonly Extent[], tolerance: number,
): Alignment | null => lines.flatMap((mine) => neighbours.flatMap((other) => ALL_LINES.map((theirs) => {
  const from = lineAt(extent, axis, mine)
  const at = lineAt(other, axis, theirs)
  return { distance: Math.abs(at - from), from, at, other }
}))).filter((one) => one.distance <= tolerance)
  .reduce<Alignment | null>((best, one) => (best === null || one.distance < best.distance ? one : best), null)

const gridded = (value: number): number => Math.round(value / GRID) * GRID

/** The guide an alignment draws, across both shapes it joins, once *extent* has landed. */
const guideOf = (axis: Axis, alignment: Alignment, extent: Extent): Guide => {
  const across: Axis = axis === 'x' ? 'y' : 'x'
  const [mine, theirs] = [span(extent, across), span(alignment.other, across)]
  return {
    axis, at: alignment.at,
    from: Math.min(mine[0], theirs[0]) - GUIDE_OVERRUN, to: Math.max(mine[1], theirs[1]) + GUIDE_OVERRUN,
  }
}

/**
 * Where *extent*, as a gesture reached it, lands: the correction to apply on each axis, and the guides
 * of the alignments that decided it. *tolerance* is `ALIGN_PIXELS` in the picture's units.
 */
export const snapped = (
  extent: Extent, lines: MovingLines, neighbours: readonly Extent[], tolerance: number, snapping: Snapping,
): Snapped => {
  const correct = (axis: Axis) => {
    const moving = lines[axis]
    const alignment = moving.length === 0 ? null : alignmentOn(axis, extent, moving, neighbours, tolerance)
    if (snapping === 'hints' || moving.length === 0) return { by: 0, alignment }
    if (alignment) return { by: alignment.at - alignment.from, alignment }
    const edge = lineAt(extent, axis, moving[0] === 'centre' ? 'low' : moving[0])
    return { by: gridded(edge) - edge, alignment }
  }
  const [x, y] = [correct('x'), correct('y')]
  const landed = {
    left: extent.left + x.by, right: extent.right + x.by, top: extent.top + y.by, bottom: extent.bottom + y.by,
  }
  return {
    dx: x.by, dy: y.by,
    guides: [
      ...(x.alignment ? [guideOf('x', x.alignment, landed)] : []),
      ...(y.alignment ? [guideOf('y', y.alignment, landed)] : []),
    ],
  }
}

/** The boxes *alias* is drawn inside, nearest first. */
const containersOf = (geometry: LayoutGeometry, alias: string): string[] => {
  const inside = new Map([...geometry.elements, ...geometry.boxes].map((shape) => [shape.alias, shape.inside]))
  const walk = (at: string | undefined, seen: readonly string[]): string[] =>
    at === undefined || seen.includes(at) ? [...seen] : walk(inside.get(at), [...seen, at])
  return walk(inside.get(alias), [])
}

/**
 * What the shapes *moving* may align to where they are: every element and box within reach of *near*,
 * but none of them, nothing they carry, and no box that holds one of them.
 */
export const neighboursOf = (
  geometry: LayoutGeometry, placement: Placement, moving: readonly string[], near: Extent,
): Extent[] => {
  const skipped = new Set(moving.flatMap((alias) =>
    [alias, ...descendantsOf(geometry, alias), ...containersOf(geometry, alias)]))
  const inReach = (extent: Extent) => Math.abs(extent.left - near.left) <= NEIGHBOUR_REACH
    && Math.abs(extent.top - near.top) <= NEIGHBOUR_REACH
  return [...placement.elements, ...placement.boxes]
    .filter(([alias, extent]) => !skipped.has(alias) && inReach(extent))
    .map(([, extent]) => extent)
}

/**
 * The guide of a line's end that lies in line with the line's other end (sketch 02·3): along the run
 * between the two, where the end at *port* on *extent* leaves straight towards *other*; null where not.
 */
export const inLineGuide = (extent: Extent, port: Port, other: Point | null): Guide | null => {
  const end = portPoint(extent, port)
  if (!other) return null
  const level = leavesLevel(port.side)
  const [mine, theirs] = level ? [end.y, other.y] : [end.x, other.x]
  if (Math.abs(mine - theirs) >= 0.5) return null
  const [from, to] = level ? [end.x, other.x] : [end.y, other.y]
  return { axis: level ? 'y' : 'x', at: mine, from: Math.min(from, to), to: Math.max(from, to) }
}
