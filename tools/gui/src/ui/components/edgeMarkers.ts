/**
 * SVG geometry for the decorations an edge carries at its ends.
 *
 * Split from `GraphCanvas.helpers` so the canvas's own module stays within the source-length
 * policy, and because these are self-contained: a path, whether it is filled, and where it
 * meets the line. Structural throughout — no shape here is named after a relationship, so the
 * canvas can draw them without knowing any ontology's vocabulary.
 */

import type { EdgeEndMarker } from './GraphCanvas.helpers'

/** Every marker the canvas can draw, so it can define one SVG marker per shape per orientation. */
export const EDGE_END_MARKERS: readonly EdgeEndMarker[] = [
  'open-arrow', 'filled-arrow', 'hollow-triangle', 'filled-diamond', 'hollow-diamond', 'ball',
]

/**
 * The SVG geometry of one end marker, in a 12x12 marker viewport pointing along +x.
 *
 * Held here rather than inline in the template so the shapes are one definition rather than
 * twelve (six markers, each needing a source- and target-oriented instance).
 */
export interface EdgeMarkerShape {
  readonly path: string
  readonly filled: boolean
  /** Where the marker meets the line, so the stroke does not poke through an unfilled shape. */
  readonly refX: number
}

const MARKER_SHAPES: Record<EdgeEndMarker, EdgeMarkerShape | null> = {
  'none': null,
  // An open arrow is two strokes, not a closed shape: the ArchiMate serving/access head.
  'open-arrow': { path: 'M 1 1 L 11 6 L 1 11', filled: false, refX: 11 },
  'filled-arrow': { path: 'M 1 1 L 11 6 L 1 11 Z', filled: true, refX: 11 },
  'hollow-triangle': { path: 'M 1 1 L 11 6 L 1 11 Z', filled: false, refX: 11 },
  'filled-diamond': { path: 'M 1 6 L 6 2 L 11 6 L 6 10 Z', filled: true, refX: 1 },
  'hollow-diamond': { path: 'M 1 6 L 6 2 L 11 6 L 6 10 Z', filled: false, refX: 1 },
  'ball': { path: 'M 6 6 m -3.5 0 a 3.5 3.5 0 1 0 7 0 a 3.5 3.5 0 1 0 -7 0', filled: true, refX: 3 },
}

export const edgeMarkerShape = (marker: EdgeEndMarker): EdgeMarkerShape | null =>
  MARKER_SHAPES[marker]

/** SVG marker element id for one shape at one end. Source markers point back along the line. */
export const edgeMarkerId = (marker: EdgeEndMarker, end: 'source' | 'target'): string =>
  `edge-${end}-${marker}`
