/**
 * Attributes that must never be copied onto an invisible hit-area clone of an SVG edge.
 *
 * Hit areas widen `stroke-width` to make thin connection lines easier to click. If a
 * `marker-*` attribute is copied along with it, and the referenced `<marker>` uses
 * `markerUnits="strokeWidth"`, the arrowhead scales with the widened stroke and renders
 * many times larger than the diagram actually specifies.
 */
export const SVG_MARKER_ATTRIBUTES = ['marker-start', 'marker-mid', 'marker-end'] as const

export function stripMarkerAttributes(element: SVGElement): void {
  for (const attr of SVG_MARKER_ATTRIBUTES) element.removeAttribute(attr)
}

const NOT_COPIED: readonly string[] = ['id', 'class', 'style', ...SVG_MARKER_ATTRIBUTES]
/** Set on every copy, whatever it is for, so no overlay is ever taken for a line and copied again. */
const OVERLAY = 'data-stroke-overlay'

/**
 * Lay a copy of each stroke of a connection's group over it, tagged with *tag*, replacing any copies an
 * earlier call laid. The copies carry the geometry only — no id, class, style or marker — so whatever
 * they are for styles them alone. A stroke inside a drawn element belongs to the element, not the line.
 *
 * Two things are laid this way: the wide invisible hit area that makes a thin line easy to click, and
 * the diagram reader's flow, which runs along the line without restyling it.
 */
export function overlayStrokes(
  group: SVGGElement, tag: string, configure: (copy: SVGElement, stroke: SVGGeometryElement) => void,
): SVGElement[] {
  for (const old of Array.from(group.querySelectorAll(`[${tag}]`))) old.remove()
  const strokes = Array.from(group.querySelectorAll<SVGGeometryElement>('path, line, polyline'))
  return strokes.flatMap((stroke) => {
    if (stroke.closest('[data-entity-id]') || stroke.hasAttribute(OVERLAY)) return []
    const copy = document.createElementNS('http://www.w3.org/2000/svg', stroke.tagName.toLowerCase())
    for (const attr of Array.from(stroke.attributes)) {
      if (!NOT_COPIED.includes(attr.name)) copy.setAttribute(attr.name, attr.value)
    }
    copy.setAttribute(tag, 'true')
    copy.setAttribute(OVERLAY, '')
    configure(copy, stroke)
    group.appendChild(copy)
    return [copy]
  })
}

/** A wide, invisible stroke over each line of a connection, so a thin line is easy to click. */
export function addConnectionHitAreas(group: SVGGElement): void {
  overlayStrokes(group, 'data-conn-hit', (hit, stroke) => {
    const strokeWidth = Number(stroke.getAttribute('stroke-width') ?? '')
    const hitWidth = Math.max(Number.isFinite(strokeWidth) ? strokeWidth * 4 : 0, 12)
    hit.setAttribute('fill', 'none')
    hit.setAttribute('stroke', 'transparent')
    hit.setAttribute('stroke-width', String(hitWidth))
    hit.setAttribute('pointer-events', 'stroke')
    hit.setAttribute('vector-effect', 'non-scaling-stroke')
  })
}
