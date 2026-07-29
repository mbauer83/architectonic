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
