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
 * A breach as the lab marks it: an annotation beside the picture, never a restyling of a line. The
 * stretch that breaks the rule is wrapped in a wide translucent halo — or, for a breach of the whole
 * relation, each end is framed — and a tag naming the rule is set *off* the line, in a box of its own,
 * with a leader back to what it names. Nothing of a mark runs along the line in a line's width, so a
 * mark cannot be read as part of the line it marks.
 */
export interface BreachMark {
  readonly key: string
  readonly breach: Breach
  readonly frames: readonly Extent[]
  readonly tag: string
  /** The tag where it is shown; null where the same tag is already shown close by. */
  readonly label: BreachLabel | null
}

/** A breach's tag as it is set off the line: its text, the box round it, and its leader. */
export interface BreachLabel {
  /** Where the text is centred on its baseline. */
  readonly at: Point
  readonly box: Extent
  /** The leader: from the edge of the box nearest what the tag names, to the stretch or frame it names. */
  readonly leader: readonly [Point, Point]
}

const clamped = (value: number, low: number, high: number): number => Math.min(high, Math.max(low, value))

/** The point of *box* nearest *to*. */
const nearestOf = (box: Extent, to: Point): Point =>
  ({ x: clamped(to.x, box.left, box.right), y: clamped(to.y, box.top, box.bottom) })

/** The rule's name as a reader is shown it: `bend-at-an-end` is tagged "bend at an end". */
export const tagOf = (breach: Breach): string => breach.rule.replaceAll('-', ' ')

/** How wide a tag's text is taken to be, in ems a character: enough to keep two tags from touching. */
const TAG_EM_WIDTH = 0.62
/** How many tag heights apart the same tag is shown twice; closer than this, once is enough. */
const SAME_TAG_APART = 6
/** How many tag heights a tag's baseline is set off the stretch it names, clear of the line and its halo. */
const TAG_OFFSET = 1.8
/** The room round a tag's text inside its box, in tag heights. */
const TAG_PADDING = 0.3
/** The heights a tag is moved by, in turn, to clear the tags already placed. */
const TAG_SHIFTS = [0, -1.8, 1.8, -3.6, 3.6]

interface PlacedTag {
  readonly tag: string
  readonly at: Point
  readonly box: Extent
}

const halfWidthOf = (tag: string, size: number): number => tag.length * size * TAG_EM_WIDTH / 2

/** The box round *tag*'s text, centred at *at* on its baseline. */
const tagBoxAt = (tag: string, at: Point, size: number): Extent => {
  const half = halfWidthOf(tag, size) + size * TAG_PADDING
  return { left: at.x - half, top: at.y - size * (0.9 + TAG_PADDING), right: at.x + half, bottom: at.y + size * (0.25 + TAG_PADDING) }
}

/** Where *tag* goes near *wanted*: the first shift that clears every tag placed, or none if it is shown nearby. */
const placedTag = (tag: string, wanted: Point, size: number, placed: readonly PlacedTag[]): PlacedTag | null => {
  if (placed.some((other) => other.tag === tag && distanceBetween(other.at, wanted) < SAME_TAG_APART * size)) return null
  const candidates = TAG_SHIFTS.map((shift): PlacedTag => {
    const at = { x: wanted.x, y: wanted.y + shift * size }
    return { tag, at, box: tagBoxAt(tag, at, size) }
  })
  return candidates.find((candidate) => !placed.some((other) => overlaps(other.box, candidate.box)))
    ?? candidates[0]
}

interface Aim {
  /** Where the tag's text would be centred, unshifted. */
  readonly wanted: Point
  /** What its leader points at. */
  readonly to: Point
}

/**
 * Where a tag naming the stretch *at* is wanted: above the middle of a stretch that runs across, to the
 * right of the middle of one that runs up and down — off the line either way.
 */
const aimBeside = (at: readonly Point[], tag: string, size: number): Aim => {
  const to = pointAlong(at, 0.5)
  const xs = at.map((point) => point.x)
  const ys = at.map((point) => point.y)
  const across = Math.max(...xs) - Math.min(...xs) >= Math.max(...ys) - Math.min(...ys)
  return across
    ? { wanted: { x: to.x, y: to.y - TAG_OFFSET * size }, to }
    : { wanted: { x: to.x + TAG_OFFSET * size + halfWidthOf(tag, size), y: to.y + size * 0.35 }, to }
}

/** Where a tag naming a framed end is wanted: above the frame's top left corner, its leader to that corner. */
const aimAbove = (frame: Extent, size: number): Aim =>
  ({ wanted: { x: frame.left, y: frame.top - TAG_OFFSET * size }, to: { x: frame.left, y: frame.top } })

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
    const aim = stretch ? aimBeside(breach.at, tag, tagSize) : frames.length > 0 ? aimAbove(frames[0], tagSize) : null
    const place = aim && placedTag(tag, aim.wanted, tagSize, placed)
    if (place) placed.push(place)
    const label = place && aim
      ? { at: place.at, box: place.box, leader: [nearestOf(place.box, aim.to), aim.to] as const }
      : null
    marks.set(key, { key, breach, frames, tag, label })
  }
  return [...marks.values()]
}
