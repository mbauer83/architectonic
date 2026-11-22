/**
 * How the lab draws its picture: where a shape is taken to drag it, where its handles sit, and a course
 * as SVG points. The order it is painted in is `labPaintOrder`; what each piece is drawn *with* is
 * PlantUML's own drawing (`labShapeDrawing`, `labLineDrawing`).
 */
import type { Extent, Point } from '../../../domain/layout/geometry'
import { centreOf } from '../../../domain/layout/geometry'
import type { Handle } from '../../../domain/layout/lab/labArrangement'
import { HANDLES } from '../../../domain/layout/lab/labArrangement'

/**
 * Where a shape is taken to drag it: its whole outline — for a grouping, its title band across the box's
 * full width included. Not the band a line keeps out of, which is only as wide as the title
 * (`routingBandOf`): the two are different regions and are kept apart.
 */
export const dragRegionOf = (now: Extent): Extent => now

/** Each resize handle of *extent*, at its corner or the middle of its side. */
export const handlesOf = (extent: Extent): { handle: Handle; at: Point }[] => {
  const middle = centreOf(extent)
  const x: Record<string, number> = { w: extent.left, e: extent.right }
  const y: Record<string, number> = { n: extent.top, s: extent.bottom }
  return HANDLES.map((handle) => ({
    handle,
    at: {
      x: [...handle].map((side) => x[side]).find((value) => value !== undefined) ?? middle.x,
      y: [...handle].map((side) => y[side]).find((value) => value !== undefined) ?? middle.y,
    },
  }))
}

export const pointsAttribute = (course: readonly Point[]): string =>
  course.map((point) => `${point.x},${point.y}`).join(' ')
