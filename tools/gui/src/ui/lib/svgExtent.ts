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
