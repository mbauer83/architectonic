/**
 * The lines a picture keeps as they are drawn once some of its shapes have moved.
 *
 * The TypeScript mirror of `src/domain/diagrams/layout/routing/kept.py`, held to it by the `kept` case of
 * `tests/fixtures/layout_geometry/routing.json`. A picture taken over keeps the lines PlantUML drew
 * (owner, 2026-11-25): only the lines touching what moved are routed again. A line is touched when an
 * element it ends at moved, or the side of a box it ends at, or when something that moved now lies across
 * the line and did not before: an element with the clearance kept round it, a box neither of the line's
 * ends is in, a text region carried with its shape. Everything else stays exactly as shown.
 */
import type { Extent, Point } from '../geometry'
import { encloses } from '../geometry'
import { IN_LINE } from '../orthogonal'
import type { RoutingScene } from './scene'
import { BUFFER, extentOf } from './scene'
import { grownOutward } from './visibility'

/** How far a shape may sit from where it was and still be where it was: a layout writes whole pixels. */
export const SAME_PLACE = 1

/** One line as it is shown: its key, its two ends and the course it runs. */
export interface ShownLine {
  readonly key: string
  readonly source: string
  readonly target: string
  readonly course: readonly Point[]
}

type Side = 'top' | 'right' | 'bottom' | 'left'
const SIDES: readonly Side[] = ['top', 'right', 'bottom', 'left']
const upright = (side: Side): boolean => side === 'left' || side === 'right'

/** Where a shape or region was (undefined where it was not) and is. */
type Moved = readonly [Extent | undefined, Extent]

const same = (one: Extent | undefined, other: Extent): boolean =>
  one !== undefined && Math.abs(one.left - other.left) <= SAME_PLACE && Math.abs(one.top - other.top) <= SAME_PLACE
  && Math.abs(one.right - other.right) <= SAME_PLACE && Math.abs(one.bottom - other.bottom) <= SAME_PLACE

const movedIn = (before: ReadonlyMap<string, Extent>, now: ReadonlyMap<string, Extent>): Map<string, Moved> =>
  new Map([...now].filter(([key, extent]) => !same(before.get(key), extent))
    .map(([key, extent]) => [key, [before.get(key), extent] as const]))

/** Whether some run of *course* passes through the inside of *region*. */
const runsThrough = (course: readonly Point[], region: Extent | undefined): boolean =>
  region !== undefined && course.slice(1).some((b, index) => {
    const a = course[index]
    return region.left < Math.max(a.x, b.x) && Math.min(a.x, b.x) < region.right
      && region.top < Math.max(a.y, b.y) && Math.min(a.y, b.y) < region.bottom
  })

const distanceToSide = (extent: Extent, side: Side, point: Point): number => upright(side)
  ? Math.abs(point.x - (side === 'left' ? extent.left : extent.right))
    + Math.max(extent.top - point.y, 0, point.y - extent.bottom)
  : Math.abs(point.y - (side === 'top' ? extent.top : extent.bottom))
    + Math.max(extent.left - point.x, 0, point.x - extent.right)

/** Whether the side of a box a line ends at, the one nearest its end, stands where it stood and spans the end. */
const stillAttached = (before: Extent, now: Extent, point: Point): boolean => {
  const side = SIDES.reduce((one, other) =>
    (distanceToSide(before, other, point) < distanceToSide(before, one, point) ? other : one))
  return upright(side)
    ? Math.abs(side === 'left' ? before.left - now.left : before.right - now.right) <= SAME_PLACE
      && now.top <= point.y && point.y <= now.bottom
    : Math.abs(side === 'top' ? before.top - now.top : before.bottom - now.bottom) <= SAME_PLACE
      && now.left <= point.x && point.x <= now.right
}

/** *end*, reached along its last run from *before*, carried on along that run onto *extent*'s border. */
const onto = (end: Point, before: Point, extent: Extent): Point => {
  if (Math.abs(end.x - before.x) <= IN_LINE && extent.left <= end.x && end.x <= extent.right) {
    return { x: end.x, y: end.y < extent.top ? extent.top : end.y > extent.bottom ? extent.bottom : end.y }
  }
  if (Math.abs(end.y - before.y) <= IN_LINE && extent.top <= end.y && end.y <= extent.bottom) {
    return { x: end.x < extent.left ? extent.left : end.x > extent.right ? extent.right : end.x, y: end.y }
  }
  return end
}

/**
 * *course*, as PlantUML drew it between *first* and *last*, with each end run carried onto the border of
 * the shape it ends at: a drawn line stops where its decoration begins, and a kept line is decorated at
 * the border, as a routed one is.
 */
export const attached = (course: readonly Point[], first: Extent, last: Extent): Point[] =>
  course.length < 2 ? [...course] : [
    onto(course[0], course[1], first), ...course.slice(1, -1),
    onto(course[course.length - 1], course[course.length - 2], last),
  ]

/** The keys of *lines*, shown over *before*, that nothing moved in *now* touches. */
export const keptLines = (before: RoutingScene, now: RoutingScene, lines: readonly ShownLine[]): ReadonlySet<string> => {
  const elements = movedIn(before.elements, now.elements)
  const boxes = movedIn(before.boxes, now.boxes)
  const text = [...movedIn(before.text, now.text).values()]
  const endMoved = (key: string, point: Point): boolean => {
    const box = boxes.get(key)
    return elements.has(key) || (box !== undefined && (box[0] === undefined || !stillAttached(box[0], box[1], point)))
  }
  /** Whether something that moved lies across *line* now and did not before. */
  const crossed = (line: ShownLine): boolean => {
    const own = (key: string) => key === line.source || key === line.target
    const ends = [extentOf(now, line.source), extentOf(now, line.target)]
    const regions: Moved[] = [
      ...[...elements].filter(([key]) => !own(key)).map(([, [was, extent]]) => [was, grownOutward(extent, BUFFER)] as const),
      ...[...boxes].filter(([key, [, box]]) => !own(key) && !ends.some((end) => encloses(box, end))).map(([, one]) => one),
      ...text,
    ]
    return regions.some(([was, region]) => runsThrough(line.course, region) && !runsThrough(line.course, was))
  }
  return new Set(lines.filter((line) => !endMoved(line.source, line.course[0])
    && !endMoved(line.target, line.course[line.course.length - 1]) && !crossed(line)).map((line) => line.key))
}
