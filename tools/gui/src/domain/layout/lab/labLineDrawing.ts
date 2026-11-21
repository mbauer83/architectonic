/**
 * A line drawn along the course the router gives it, the way the composer draws one: PlantUML's own
 * stroke along a polyline with rounded bends, stopped short of a hollow head, and PlantUML's own
 * decorations carried from the frame they were drawn in to the line's new ends.
 *
 * The TypeScript mirror of `relation_drawing.rounded_path` and of `relation_decorations`
 * (`heading_at_end`, `stopping_short`, the turn `Motion.facing` makes), for the lab's drag frames:
 * only where a line goes is decided here. What it is drawn with — colour, weight, dashes, the shape
 * of a head — is PlantUML's drawing, handed over by the lab's geometry and never restated.
 */
import type { Point } from '../geometry'
import { distanceBetween } from '../geometry'
import { pointAlong } from '../orthogonal'
import type { DrawingNode, LabLineDrawing, LabLineEnd } from './labGeometry'

/** How round a bend is drawn. */
const BEND_RADIUS = 6
/** Below this a bend is drawn sharp: there is no room for a curve worth drawing. */
const SHARP_BELOW = 0.5
/** How much of each run is left straight between two rounded bends. */
const STRAIGHT_LEFT = 1
/** How far back along a line its heading is taken from. */
const HEADING_TAKEN_OVER = 8
/** The shortest run a line keeps when it stops short of a decoration. */
const SHORTEST_RUN = 1

/** *value* as a coordinate is written: four places, no trailing zeros (`svg_path_data.written_number`). */
const written = (value: number): string => value.toFixed(4).replace(/0+$/, '').replace(/\.$/, '') || '0'
const at = (point: Point): string => `${written(point.x)},${written(point.y)}`

const towards = (start: Point, end: Point, distance: number): Point => {
  const length = distanceBetween(start, end)
  return { x: start.x + (end.x - start.x) / length * distance, y: start.y + (end.y - start.y) / length * distance }
}

/** The path data of a line through *course* with each bend rounded as far as its two runs allow. */
export const roundedPath = (course: readonly Point[]): string => {
  const bends = course.slice(1, -1).map((bend, index) => {
    const before = course[index]
    const after = course[index + 2]
    const radius = Math.min(
      BEND_RADIUS,
      (distanceBetween(before, bend) - STRAIGHT_LEFT) / 2,
      (distanceBetween(bend, after) - STRAIGHT_LEFT) / 2,
    )
    return radius < SHARP_BELOW
      ? `L${at(bend)}`
      : `L${at(towards(bend, before, radius))} Q${at(bend)} ${at(towards(bend, after, radius))}`
  })
  return [`M${at(course[0])}`, ...bends, `L${at(course[course.length - 1])}`].join(' ')
}

/** Which way *course* is going when it ends, taken over its last few pixels: a unit vector. */
export const headingAtEnd = (course: readonly Point[]): Point => {
  const end = course[course.length - 1]
  const back = [...course.slice(0, -1)].reverse()
    .find((point) => distanceBetween(point, end) >= HEADING_TAKEN_OVER) ?? course[0]
  const length = distanceBetween(back, end)
  return length > 0 ? { x: (end.x - back.x) / length, y: (end.y - back.y) / length } : { x: 0, y: 1 }
}

const pulledBack = (end: Point, before: Point, gap: number): Point => {
  const run = distanceBetween(before, end)
  if (run <= 0) return end
  const kept = Math.max(0, Math.min(gap, run - SHORTEST_RUN))
  return { x: end.x + (before.x - end.x) / run * kept, y: end.y + (before.y - end.y) / run * kept }
}

/** *course* with its two ends pulled back along their own runs by the gaps the line is drawn with. */
export const stoppingShort = (course: readonly Point[], gapAtStart: number, gapAtEnd: number): Point[] => [
  pulledBack(course[0], course[1], gapAtStart),
  ...course.slice(1, -1),
  pulledBack(course[course.length - 1], course[course.length - 2], gapAtEnd),
]

/** A turn about *pivot* by *degrees* that carries the pivot to *to* (`svg_markup.Motion`). */
export interface Motion {
  readonly pivot: Point
  readonly to: Point
  readonly degrees: number
}

/**
 * How an end's decorations are carried from the frame they were drawn in to the end of *course*,
 * facing the way the course arrives there (`Motion.facing`).
 */
export const decorationMotion = (end: Pick<LabLineEnd, 'at' | 'heading'>, course: readonly Point[]): Motion => {
  const [headingX, headingY] = end.heading
  const wanted = headingAtEnd(course)
  const cos = headingX * wanted.x + headingY * wanted.y
  const sin = headingX * wanted.y - headingY * wanted.x
  return {
    pivot: { x: end.at[0], y: end.at[1] },
    to: course[course.length - 1],
    degrees: Math.atan2(sin, cos) * 180 / Math.PI,
  }
}

/** *motion* as an SVG transform: the pivot to the origin, the turn, then the origin to where it goes. */
export const transformOf = ({ pivot, to, degrees }: Motion): string =>
  `translate(${written(to.x)} ${written(to.y)}) rotate(${written(degrees)}) `
  + `translate(${written(-pivot.x)} ${written(-pivot.y)})`

export interface DrawnLine {
  readonly line: DrawingNode
  readonly ends: readonly { readonly marks: readonly DrawingNode[]; readonly transform: string }[]
  readonly label: { readonly texts: readonly DrawingNode[]; readonly transform: string } | null
}

/**
 * A line drawn along *course*, which runs from its source: PlantUML's stroke along it, its decorations
 * carried to its ends, its label to the middle of it.
 */
export const drawnLine = (drawing: LabLineDrawing, course: readonly Point[]): DrawnLine => {
  const [atSource, atTarget] = drawing.ends
  const labelAt = pointAlong(course, 0.5)
  const labelShift = (centre: readonly [number, number]): string =>
    `translate(${written(labelAt.x - centre[0])} ${written(labelAt.y - centre[1])})`
  const d = roundedPath(stoppingShort(course, atSource.gap, atTarget.gap))
  return {
    line: { ...drawing.line, attributes: { ...drawing.line.attributes, d } },
    ends: [
      { marks: atSource.marks, transform: transformOf(decorationMotion(atSource, [...course].reverse())) },
      { marks: atTarget.marks, transform: transformOf(decorationMotion(atTarget, course)) },
    ],
    label: drawing.label && {
      texts: drawing.label.texts,
      transform: labelShift(drawing.label.centre),
    },
  }
}
