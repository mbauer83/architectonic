/**
 * The diagram reader's marks on a rendered picture: what steps back, what stays, and the flow.
 *
 * Dimmed, never hidden. Whatever the reading does not reach takes `reading-dim`, which the page's style
 * lowers in strength and lifts part-way under the pointer; it stays where it is and stays clickable.
 * Flow is laid over a relation's line as a copy of its stroke (`overlayStrokes`), so the line itself is
 * never restyled, and an export, which the server draws from the stored body, cannot carry it.
 *
 * Generic over every diagram type: it reads only the element map the type's viewer resolved.
 */
import { centreOf, distanceBetween } from '../../domain/layout/geometry'
import { pictureExtentOf } from './svgExtent'
import { overlayStrokes } from './svgHitAreas'

/** How a relation's flow runs: travelling along its model direction, or, without one, an even pulse. */
export interface FlowOf {
  readonly directed: boolean
  /** What the relation's target is drawn as: the end its travelling dots run towards. */
  readonly target: readonly Element[]
}

export interface ReadingPaint {
  /** Entities at full strength: the selection and what it reaches. */
  readonly lit: ReadonlySet<string>
  /** Relations at full strength: the ones the reach crossed. */
  readonly relations: ReadonlySet<string>
  /** Relations whose flow is shown, while the flow toggle is on; null while it is off. */
  readonly flow: ReadonlyMap<string, FlowOf> | null
}

const FLOW = 'data-reading-flow'
const MARKS = ['reading-dim', 'reading-lit']

/**
 * Whether a drawn stroke runs from the relation's source to its target. PlantUML draws `B <-- A` from
 * B, so the path's own direction says nothing; the end nearer the target's shape does.
 */
const runsTowards = (stroke: SVGGeometryElement, target: readonly Element[]): boolean => {
  try {
    const length = stroke.getTotalLength()
    const start = stroke.getPointAtLength(0)
    const end = stroke.getPointAtLength(length)
    const centres = target.flatMap((element) => pictureExtentOf(element) ?? []).map(centreOf)
    if (centres.length === 0) return true
    const nearest = (point: DOMPoint) => Math.min(...centres.map((centre) => distanceBetween(centre, point)))
    return nearest(end) <= nearest(start)
  } catch { return true }
}

const flowClass = (stroke: SVGGeometryElement, flow: FlowOf): string => {
  if (!flow.directed) return 'reading-flow reading-flow--pulse'
  return runsTowards(stroke, flow.target) ? 'reading-flow' : 'reading-flow reading-flow--reverse'
}

/** Take every mark of an earlier reading off the picture. */
export const clearReading = (svg: SVGSVGElement): void => {
  svg.classList.remove('reading-on')
  for (const element of Array.from(svg.querySelectorAll(MARKS.map((mark) => `.${mark}`).join(', ')))) {
    element.classList.remove(...MARKS)
  }
  for (const overlay of Array.from(svg.querySelectorAll(`[${FLOW}]`))) overlay.remove()
}

/** Mark *svg* for a reading, replacing whatever an earlier one marked; null clears it. */
export const paintReading = (
  svg: SVGSVGElement,
  nodes: ReadonlyMap<string, readonly Element[]>,
  edges: ReadonlyMap<string, readonly Element[]>,
  paint: ReadingPaint | null,
): void => {
  clearReading(svg)
  if (!paint) return
  svg.classList.add('reading-on')
  for (const [id, elements] of nodes) {
    if (!paint.lit.has(id)) for (const element of elements) element.classList.add('reading-dim')
  }
  for (const [id, elements] of edges) {
    const mark = paint.relations.has(id) ? 'reading-lit' : 'reading-dim'
    for (const element of elements) element.classList.add(mark)
  }
  for (const [id, flow] of paint.flow ?? []) {
    for (const group of edges.get(id) ?? []) {
      if (!(group instanceof SVGGElement)) continue
      overlayStrokes(group, FLOW, (copy, stroke) => copy.setAttribute('class', flowClass(stroke, flow)))
    }
  }
}
