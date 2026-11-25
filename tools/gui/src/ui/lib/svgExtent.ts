import type { Extent } from '../../domain/layout/geometry'
import { unionOf } from '../../domain/layout/geometry'

/**
 * Where an element of a rendered picture is drawn, in the picture's own units; null where the browser
 * cannot say (an element that is not drawn, or a DOM with no layout, as under test).
 *
 * One reading for the diagram reader's three needs — which end of a line a relation runs to, the
 * reading order the keyboard walks, and the part of the picture a reading frames.
 */
export const pictureExtentOf = (element: Element): Extent | null => {
  const { getBBox } = element as Partial<SVGGraphicsElement>
  if (typeof getBBox !== 'function') return null
  try {
    const box = getBBox.call(element)
    return { left: box.x, top: box.y, right: box.x + box.width, bottom: box.y + box.height }
  } catch { return null }
}

/** Where a set of drawn elements is, together; null where none of them is drawn. */
export const drawnExtentOf = (elements: readonly Element[]): Extent | null => {
  const extents = elements.flatMap((element) => pictureExtentOf(element) ?? [])
    .filter((extent) => extent.right > extent.left || extent.bottom > extent.top)
  return extents.length > 0 ? unionOf(extents) : null
}

/**
 * Everything a picture draws, in its own units, for a window to frame: the whole drawing, not its first
 * group. PlantUML wraps everything in one root `<g>`, so the two used to agree — but a type that draws its
 * own SVG need not: GSN's first group is a single connector, whose box is a line with no height, so the
 * fit read "nothing to fit" and the diagram opened at its natural size, clipped (B89). Where the browser
 * cannot measure it, the picture's `viewBox`, else its stated size. Null for a picture with no extent.
 */
export const drawingExtentOf = (svg: SVGSVGElement): Extent | null => {
  const viewBox = svg.viewBox?.baseVal
  const stated = (name: 'width' | 'height', laidOut: number): number => {
    const value = Number(svg.getAttribute(name) ?? '')
    return Number.isFinite(value) && value > 0 ? value : laidOut
  }
  const extent = pictureExtentOf(svg)
    ?? (viewBox && viewBox.width > 0 && viewBox.height > 0
      ? { left: viewBox.x, top: viewBox.y, right: viewBox.x + viewBox.width, bottom: viewBox.y + viewBox.height }
      : { left: 0, top: 0, right: stated('width', svg.clientWidth), bottom: stated('height', svg.clientHeight) })
  return extent.right > extent.left && extent.bottom > extent.top ? extent : null
}
