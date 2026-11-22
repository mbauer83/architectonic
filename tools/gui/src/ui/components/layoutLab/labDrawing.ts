/**
 * How the lab draws its picture: where a shape is taken to drag it, where its handles sit, how a breach
 * is marked, and a course as SVG points. The order it is painted in is `labPaintOrder`; what each piece
 * is drawn *with* is PlantUML's own drawing (`labShapeDrawing`, `labLineDrawing`).
 */
import type { Extent, Point } from '../../../domain/layout/geometry'
import { centreOf, distanceBetween, overlaps } from '../../../domain/layout/geometry'
import type { Handle } from '../../../domain/layout/lab/labArrangement'
import { HANDLES } from '../../../domain/layout/lab/labArrangement'
import type { Breach } from '../../../domain/layout/lab/labBreaches'
import { pointAlong } from '../../../domain/layout/orthogonal'

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

/**
 * A breach as the lab marks it: the stretch of line that breaks the rule, or a frame round each end
 * where the breach is of the whole relation, and a tag naming the rule by the middle of the stretch or
 * the corner of the first frame — so a mark never reads as a highlight with no reason given.
 */
export interface BreachMark {
  readonly key: string
  readonly breach: Breach
  readonly frames: readonly Extent[]
  readonly tag: string
  /** Where the tag's text is centred on its baseline; null where the same tag is already shown close by. */
  readonly tagAt: Point | null
}

/** The rule's name as a reader is shown it: `bend-at-an-end` is tagged "bend at an end". */
export const tagOf = (breach: Breach): string => breach.rule.replaceAll('-', ' ')

/** How wide a tag's text is taken to be, in ems a character: enough to keep two tags from touching. */
const TAG_EM_WIDTH = 0.62
/** How many tag heights apart the same tag is shown twice; closer than this, once is enough. */
const SAME_TAG_APART = 6
/** The heights a tag is moved by, in turn, to clear the tags already placed. */
const TAG_SHIFTS = [0, -1.2, 1.2, -2.4, 2.4]

interface PlacedTag {
  readonly tag: string
  readonly at: Point
  readonly extent: Extent
}

const tagExtent = (tag: string, at: Point, size: number): Extent => {
  const half = tag.length * size * TAG_EM_WIDTH / 2
  return { left: at.x - half, top: at.y - size, right: at.x + half, bottom: at.y + size * 0.25 }
}

/** Where *tag* goes near *wanted*: the first shift that clears every tag placed, or none if it is shown nearby. */
const placedTag = (tag: string, wanted: Point, size: number, placed: readonly PlacedTag[]): PlacedTag | null => {
  if (placed.some((other) => other.tag === tag && distanceBetween(other.at, wanted) < SAME_TAG_APART * size)) return null
  const candidates = TAG_SHIFTS.map((shift): PlacedTag => {
    const at = { x: wanted.x, y: wanted.y + shift * size }
    return { tag, at, extent: tagExtent(tag, at, size) }
  })
  return candidates.find((candidate) => !placed.some((other) => overlaps(other.extent, candidate.extent)))
    ?? candidates[0]
}

/**
 * One mark per breach; a breach found twice over the same stretch is marked once. *endsOf* is where a
 * relation's two ends are now; *tagSize* how tall a tag is drawn, in the picture's units.
 */
export const breachMarksOf = (
  breaches: readonly Breach[], endsOf: (relation: number) => readonly Extent[], tagSize: number,
): BreachMark[] => {
  const marks = new Map<string, BreachMark>()
  const placed: PlacedTag[] = []
  for (const breach of breaches) {
    const key = `${breach.relation}:${breach.rule}:${pointsAttribute(breach.at)}`
    if (marks.has(key)) continue
    const stretch = breach.at.length >= 2
    const frames = stretch ? [] : endsOf(breach.relation)
    const tag = tagOf(breach)
    const wanted = stretch
      ? pointAlong(breach.at, 0.5)
      : frames.length > 0 ? { x: frames[0].left, y: frames[0].top } : null
    const place = wanted && placedTag(tag, { x: wanted.x, y: wanted.y - tagSize / 2 }, tagSize, placed)
    if (place) placed.push(place)
    marks.set(key, { key, breach, frames, tag, tagAt: place ? place.at : null })
  }
  return [...marks.values()]
}

