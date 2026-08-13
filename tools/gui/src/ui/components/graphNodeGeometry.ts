import { wrapLabel } from './GraphCanvas.helpers'

/**
 * How much room one rendered graph node occupies, in node-local coordinates.
 *
 * One definition, used by both halves of the canvas. The renderer needs it to place the
 * label's backing rectangle; the cluster layout needs it to size a grid cell. When each
 * derived its own estimate the two disagreed — the layout guessed a node's width from the
 * raw label length while the renderer measured the *wrapped* label, so cells were sized for
 * text that was never drawn and grids that looked correct on paper overlapped on screen.
 *
 * Coordinates are relative to the node's centre: `top` is negative, `bottom` positive.
 */

/** Radius of the node's own shape, and of the extra ring an anchor carries. */
export const NODE_SHAPE_RADIUS = 24
export const ANCHOR_HALO_RADIUS = 32

/** Clear air between a node's boundary and the marker an edge ends in. */
const MARKER_GAP = 2

/**
 * How far short of a node's centre an edge stops, so the decoration at that end sits beside the
 * node rather than under it.
 *
 * Here rather than at the canvas, and derived rather than spelled: the call site used to carry
 * `isAnchor ? 34 : 26`, which is these radii plus the gap, written a second time. The two agreed
 * by luck, and only until one of them moved.
 */
export const edgeEndRadius = (isAnchor: boolean): number =>
  (isAnchor ? ANCHOR_HALO_RADIUS : NODE_SHAPE_RADIUS) + MARKER_GAP

const CHAR_WIDTH = 6
const LINE_HEIGHT = 12
const LABEL_PADDING = 10
const LABEL_BOX_SLACK = 6

/** Baseline of the first label line, below the shape. */
const labelBaseline = (isAnchor: boolean): number => (isAnchor ? 46 : 40)

export interface NodeLabelBox { x: number; y: number; width: number; height: number }

/** The label's backing rectangle: what the renderer draws behind the text. */
export const nodeLabelBox = (label: string, type: string, isAnchor: boolean): NodeLabelBox => {
  const lines = wrapLabel(label)
  // The first line is prefixed with the abbreviated type ("APP: "), so it is the widest
  // unless a later line happens to be longer.
  const firstLength = type.length + 2 + (lines[0]?.length ?? 0)
  const longest = Math.max(firstLength, ...lines.slice(1).map((line) => line.length))
  const width = longest * CHAR_WIDTH + LABEL_PADDING
  const height = lines.length * LINE_HEIGHT + LABEL_BOX_SLACK
  return { x: -width / 2, y: labelBaseline(isAnchor) - 11, width, height }
}

export interface NodeExtent { width: number; height: number; top: number; bottom: number }

/** The full box the node occupies: its shape and its label together. */
export const nodeExtent = (label: string, type: string, isAnchor: boolean): NodeExtent => {
  const box = nodeLabelBox(label, type, isAnchor)
  const radius = isAnchor ? ANCHOR_HALO_RADIUS : NODE_SHAPE_RADIUS
  const top = -radius
  const bottom = Math.max(radius, box.y + box.height)
  return { width: Math.max(radius * 2, box.width), height: bottom - top, top, bottom }
}
