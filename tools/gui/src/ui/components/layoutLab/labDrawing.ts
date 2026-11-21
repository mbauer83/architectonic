/**
 * How the lab draws its picture: where text goes when its shape moves or is resized, the order shapes
 * are painted in, where a shape's handles sit, and a course as SVG points.
 *
 * Text keeps PlantUML's own setting — its words, their measured widths, their lines — carried with the
 * shape and kept central in it when the shape is resized. The server's picture re-wraps a resized
 * label; the lab does not try to.
 */
import type { Extent, Point } from '../../../domain/layout/geometry'
import { centreOf, heightOf, widthOf } from '../../../domain/layout/geometry'
import type { Handle } from '../../../domain/layout/lab/labArrangement'
import { HANDLES, childrenOf } from '../../../domain/layout/lab/labArrangement'
import type { LabBox, LabGeometry, LabWord } from '../../../domain/layout/lab/labGeometry'

export interface PlacedWord {
  readonly text: string
  readonly x: number
  readonly y: number
  /** The width PlantUML measured, which the drawing holds the word to. */
  readonly width: number
}

/** An element's words where they go now: carried with it, and kept central where it was resized. */
export const elementWords = (words: readonly LabWord[], drawn: Extent, now: Extent): PlacedWord[] => {
  const dx = now.left - drawn.left + (widthOf(now) - widthOf(drawn)) / 2
  const dy = now.top - drawn.top + (heightOf(now) - heightOf(drawn)) / 2
  return words.map((word) => ({ text: word.text, x: word.x + dx, y: word.y + dy, width: word.width }))
}

/**
 * Where a shape is taken to drag it: its whole outline — for a grouping, its title band across the box's
 * full width included. Not the band a line keeps out of, which is only as wide as the title
 * (`routingBandOf`): the two are different regions and are kept apart.
 */
export const dragRegionOf = (now: Extent): Extent => now

/** A box's title where it goes now: across the middle of the box, as far below its top as it was. */
export const titleWords = (box: LabBox, now: Extent): PlacedWord[] => {
  const dx = centreOf(now).x - centreOf(box.extent).x
  const dy = now.top - box.extent.top
  return box.words.map((word) => ({ text: word.text, x: word.x + dx, y: word.y + dy, width: word.width }))
}

export interface Painted {
  readonly alias: string
  readonly isBox: boolean
}

/**
 * Every shape back to front, as the composer paints: a box and everything in it are one unit,
 * siblings as PlantUML drew them, boxes before the elements beside them. The unit holding *lifted* —
 * the shape last pressed — goes in front of its siblings, so what was moved is brought into view.
 */
export const paintOrder = (geometry: LabGeometry, lifted: string | null): Painted[] => {
  const boxes = new Set(geometry.boxes.map((box) => box.alias))
  const children = childrenOf(geometry)
  const inside = new Map([...geometry.boxes, ...geometry.elements].map((shape) => [shape.alias, shape.inside]))
  const raised = new Set<string>()
  for (let alias = lifted; alias !== null && !raised.has(alias); alias = inside.get(alias) ?? null) raised.add(alias)
  const walk = (parent: string | null): Painted[] => {
    const siblings = children.get(parent) ?? []
    const ordered = [
      ...siblings.filter((alias) => !raised.has(alias)),
      ...siblings.filter((alias) => raised.has(alias)),
    ]
    return ordered.flatMap((alias) => [{ alias, isBox: boxes.has(alias) }, ...walk(alias)])
  }
  return walk(null)
}

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

