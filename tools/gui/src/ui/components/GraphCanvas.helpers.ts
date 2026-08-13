/**
 * Pure geometry/presentation helpers for the generic graph canvas: node shape
 * polygons, label wrapping, contrast-aware text color, edge paths, multiplicity
 * label positions, and viewBox fitting. No architecture, assurance, or
 * viewpoint imports — consumers supply meaning; this module supplies pixels.
 */

export interface NodeVisual {
  readonly color: string
  readonly shape: 'circle' | 'diamond' | 'triangle' | 'square'
  readonly iconLetter: string | null
  /** Inner SVG markup for a glyph drawn inside the node shape (e.g. an ArchiMate type
   * icon), supplied by the domain-aware consumer. The canvas renders it opaquely — it
   * never resolves glyphs itself. Null/absent ⇒ the node falls back to its type text. */
  readonly glyph?: string | null
}

/**
 * Decorations an edge may carry at either end.
 *
 * Structural names, never relationship names: the canvas draws a hollow triangle without
 * knowing that a hollow triangle means realization, so a second modelling language can ask for
 * the same shapes. The vocabulary belongs to whichever surface supplies the `edgeVisual`
 * callback; see `tests/architecture/test_generic_graph_module_boundaries.py`.
 */
export type EdgeEndMarker =
  | 'none'
  | 'open-arrow'
  | 'filled-arrow'
  | 'hollow-triangle'
  | 'filled-diamond'
  | 'hollow-diamond'
  | 'ball'

export interface EdgeVisual {
  readonly stroke: string | null
  readonly strokeWidth: number | null
  readonly dashArray: string | undefined
  /** Marker at the edge's source end. Absent renders as `none`. */
  readonly sourceMarker?: EdgeEndMarker
  /** Marker at the edge's target end. Absent keeps the plain arrowhead. */
  readonly targetMarker?: EdgeEndMarker
}


const SHAPE_SIDES: Record<NodeVisual['shape'], number> = { circle: 24, diamond: 4, square: 4, triangle: 3 }
const SHAPE_ROTATION: Record<NodeVisual['shape'], number> = { circle: 0, diamond: 0, square: Math.PI / 4, triangle: -Math.PI / 2 }

/** Renders every node shape as a regular polygon (a 24-gon reads as a circle) so the
 * canvas can show real shape variety with one SVG element type — no per-shape
 * template branching. */
export const nodeShapePoints = (shape: NodeVisual['shape'], radius: number): string => {
  const sides = SHAPE_SIDES[shape]
  const rotation = SHAPE_ROTATION[shape]
  const points: string[] = []
  for (let i = 0; i < sides; i++) {
    const angle = rotation + (i / sides) * Math.PI * 2
    points.push(`${(Math.cos(angle) * radius).toFixed(2)},${(Math.sin(angle) * radius).toFixed(2)}`)
  }
  return points.join(' ')
}

/** Legible text color for glyphs drawn on top of a node fill: dark ink on light fills,
 * white on dark fills, decided by perceived (YIQ) brightness. Non-hex input (never
 * produced by the fill pipeline) defaults to dark ink. */
export const contrastTextColor = (fillColor: string): string => {
  const match = /^#([0-9a-f]{6})$/i.exec(fillColor)
  if (!match) return '#252327'
  const [r, g, b] = [0, 2, 4].map((offset) => parseInt(match[1].slice(offset, offset + 2), 16))
  const brightness = (r * 299 + g * 587 + b * 114) / 1000
  return brightness >= 145 ? '#252327' : '#ffffff'
}

export interface ViewBoxRect { x: number; y: number; w: number; h: number }

/** ViewBox that fits every node with padding, aspect-corrected to the container — the
 * one-click answer to results rendered off-viewport. Falls back to the container rect
 * when there is nothing to fit. */
export const fitViewBox = (
  nodes: readonly { x: number; y: number }[],
  containerWidth: number,
  containerHeight: number,
  padding = 80,
): ViewBoxRect => {
  if (nodes.length === 0 || containerWidth <= 0 || containerHeight <= 0) {
    return { x: 0, y: 0, w: Math.max(containerWidth, 1), h: Math.max(containerHeight, 1) }
  }
  const xs = nodes.map((n) => n.x)
  const ys = nodes.map((n) => n.y)
  const minX = Math.min(...xs) - padding
  const maxX = Math.max(...xs) + padding
  const minY = Math.min(...ys) - padding
  const maxY = Math.max(...ys) + padding
  const width = maxX - minX
  const height = maxY - minY
  const containerRatio = containerWidth / containerHeight
  const contentRatio = width / height
  if (contentRatio > containerRatio) {
    const correctedHeight = width / containerRatio
    return { x: minX, y: minY - (correctedHeight - height) / 2, w: width, h: correctedHeight }
  }
  const correctedWidth = height * containerRatio
  return { x: minX - (correctedWidth - width) / 2, y: minY, w: correctedWidth, h: height }
}

/** Word-aware label wrapping for SVG tspans: up to `maxLines` lines of `maxChars`,
 * with an ellipsis when content remains — mid-word truncation was producing misreadings
 * that reached real review artifacts. The full name always travels in the node tooltip. */
export const wrapLabel = (label: string, maxChars = 14, maxLines = 2): string[] => {
  const words = label.split(/\s+/).filter((word) => word.length > 0)
  const wrapped: string[] = []
  let current = ''
  for (const word of words) {
    const candidate = current === '' ? word : `${current} ${word}`
    if (candidate.length <= maxChars) {
      current = candidate
      continue
    }
    if (current !== '') wrapped.push(current)
    current = word
  }
  if (current !== '') wrapped.push(current)
  const lines = wrapped.slice(0, maxLines).map(
    (line) => (line.length > maxChars ? `${line.slice(0, maxChars - 1)}…` : line),
  )
  if (wrapped.length > maxLines && !lines[maxLines - 1].endsWith('…')) {
    const last = lines[maxLines - 1]
    lines[maxLines - 1] = last.length >= maxChars ? `${last.slice(0, maxChars - 1)}…` : `${last}…`
  }
  return lines.length > 0 ? lines : ['']
}

interface PositionedNode {
  readonly id: string
  readonly x: number
  readonly y: number
}

/**
 * SVG path for an edge: orthogonal elbows in cluster layout, a straight segment otherwise.
 *
 * **Both ends stop short of their node's centre**, each by its own node's radius, so the
 * decoration at either end sits beside the node rather than under it. Only the target end was
 * backed off for as long as this function existed, and the parameter was named `targetRadius`:
 * every `marker-start` the ontology declares — the composition and aggregation diamonds, the
 * assignment ball — was therefore drawn beneath the source node's own shape. The ball had never
 * once been visible.
 *
 * `radiusOf` is asked per node rather than given as a number, because the two ends can want
 * different answers: an anchor carries a larger ring, and the source's anchor state was not
 * even consulted before. It says nothing about *why* a node is larger, which keeps this
 * ignorant of anchors and selection.
 *
 * Empty string when either endpoint is missing from the node set.
 */
export const edgePathFor = (
  nodes: readonly PositionedNode[],
  edge: { readonly source: string; readonly target: string },
  clusterLayout: boolean,
  radiusOf: (nodeId: string) => number = () => 26,
): string => {
  const src = nodes.find((n) => n.id === edge.source)
  const tgt = nodes.find((n) => n.id === edge.target)
  if (!src || !tgt) return ''
  const sourceRadius = radiusOf(edge.source)
  const targetRadius = radiusOf(edge.target)
  if (clusterLayout) {
    const midY = (src.y + tgt.y) / 2
    // The elbow leaves the source vertically and arrives vertically; back both off along that
    // axis, and only where the segment is long enough to give the back-off room.
    const departure = midY >= src.y ? sourceRadius : -sourceRadius
    const startY = Math.abs(midY - src.y) > sourceRadius ? src.y + departure : src.y
    const approach = tgt.y >= midY ? -targetRadius : targetRadius
    const endY = Math.abs(tgt.y - midY) > targetRadius ? tgt.y + approach : tgt.y
    return `M ${src.x} ${startY} V ${midY} H ${tgt.x} V ${endY}`
  }
  const dx = tgt.x - src.x
  const dy = tgt.y - src.y
  const len = Math.sqrt(dx * dx + dy * dy)
  // Overlapping nodes have no room for either decoration, and inverting the segment to make
  // room would draw an edge pointing the wrong way. Keep the honest centre-to-centre line and
  // let the layout separate them.
  if (len <= sourceRadius + targetRadius) return `M ${src.x} ${src.y} L ${tgt.x} ${tgt.y}`
  const sx = src.x + (dx / len) * sourceRadius
  const sy = src.y + (dy / len) * sourceRadius
  const ex = tgt.x - (dx / len) * targetRadius
  const ey = tgt.y - (dy / len) * targetRadius
  return `M ${sx.toFixed(2)} ${sy.toFixed(2)} L ${ex.toFixed(2)} ${ey.toFixed(2)}`
}

/** SVG coords for a multiplicity label at `frac` (0=source, 1=target) along an edge,
 * offset 8px perpendicular-ish above the line for legibility. */
export const edgeCardPosFor = (
  nodes: readonly PositionedNode[],
  edge: { readonly source: string; readonly target: string },
  frac: number,
): { x: number; y: number } => {
  const src = nodes.find((n) => n.id === edge.source)
  const tgt = nodes.find((n) => n.id === edge.target)
  if (!src || !tgt) return { x: 0, y: 0 }
  const dx = tgt.x - src.x
  const dy = tgt.y - src.y
  const len = Math.max(Math.sqrt(dx * dx + dy * dy), 1)
  return {
    x: src.x + dx * frac - (dy / len) * 8,
    y: src.y + dy * frac + (dx / len) * 8,
  }
}
