/**
 * How the canvas draws its picture: where a shape is taken to drag it, where its handles sit, how a
 * breach is marked, and a course as SVG points. The order it is painted in is `labPaintOrder`; what each piece
 * is drawn *with* is PlantUML's own drawing (`labShapeDrawing`, `labLineDrawing`).
 */
import type { Extent, Point } from '../../../domain/layout/geometry'
import { centreOf } from '../../../domain/layout/geometry'
import type { Handle } from '../../../domain/layout/lab/labArrangement'
import { HANDLES } from '../../../domain/layout/lab/labArrangement'
import type { Breach } from '../../../domain/layout/lab/labBreaches'
import { distinctBreaches } from '../../../domain/layout/lab/labBreaches'

/**
 * Where a shape is taken to drag it. An element: its whole outline. A box with a title: its title band,
 * *bandDepth* deep, across the box's full width (owner rule) — its body selects rather than drags, so a
 * box can be pressed without moving everything in it. Not the band a line keeps out of, which is only
 * as wide as the title (`routingBandOf`): the two are different regions and are kept apart.
 */
export const dragRegionOf = (now: Extent, bandDepth?: number): Extent =>
  bandDepth === undefined ? now : { ...now, bottom: Math.min(now.bottom, now.top + bandDepth) }

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

/**
 * A breach as the canvas marks it while the layout is checked: never a restyling of a line, and never
 * a word on the picture. The stretch that breaks the rule is traced in a thin dashed band — or, for a
 * breach of the whole relation, each end is outlined — and what it breaks is said on hover.
 */
export interface BreachMark {
  readonly key: string
  readonly breach: Breach
  readonly frames: readonly Extent[]
}

/** One mark per breach a reader is shown; *endsOf* is where a relation's two ends are now. */
export const breachMarksOf = (
  breaches: readonly Breach[], endsOf: (relation: number) => readonly Extent[],
): BreachMark[] =>
  distinctBreaches(breaches).map(({ key, breach }) =>
    ({ key, breach, frames: breach.at.length >= 2 ? [] : endsOf(breach.relation) }))

