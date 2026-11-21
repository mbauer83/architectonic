/**
 * The orthogonal visibility graph's lines, and what blocks a step along one of them.
 *
 * The TypeScript mirror of `src/domain/diagrams/layout/routing/visibility.py`: candidate lines at
 * every element's edges moved out by BUFFER, every text region's likewise, every box border moved
 * BORDER_OFFSET either side, all whole numbers. For one connector, an element (grown), a text region
 * and a wall — a box holding neither of its ends, or one that is an end — block; a run along any
 * box border closer than the clearance blocks too, and a step out of the connector's bounds: the
 * smallest box holding both ends, crossed into a box holding the target once, out of one holding the
 * source once.
 */
import type { Extent, Point } from '../geometry'
import { encloses } from '../geometry'
import { Graph } from './graph'
import type { Stubs } from './lines'
import { Lines } from './lines'
import type { RoutingScene } from './scene'
import { BORDER_OFFSET, BUFFER, IDEAL_SEPARATION, byText, extentOf, sameExtent } from './scene'

const CELL = 128
const ROOM_LOOKED_FOR = 60

/** What a run in a channel already full counts as, in routes alongside. */
export const FULL = 100

export const grownOutward = (extent: Extent, by: number): Extent => ({
  left: Math.floor(extent.left - by),
  top: Math.floor(extent.top - by),
  right: Math.ceil(extent.right + by),
  bottom: Math.ceil(extent.bottom + by),
})

const enters = (rect: Extent, a: Point, b: Point): boolean =>
  a.y === b.y
    ? rect.top < a.y && a.y < rect.bottom &&
      Math.max(rect.left, Math.min(a.x, b.x)) < Math.min(rect.right, Math.max(a.x, b.x))
    : rect.left < a.x && a.x < rect.right &&
      Math.max(rect.top, Math.min(a.y, b.y)) < Math.min(rect.bottom, Math.max(a.y, b.y))

class RectIndex {
  private readonly cells = new Map<string, Extent[]>()

  constructor(rects: readonly Extent[]) {
    for (const rect of rects) {
      for (let column = Math.floor(rect.left / CELL); column <= Math.floor(rect.right / CELL); column += 1) {
        for (let row = Math.floor(rect.top / CELL); row <= Math.floor(rect.bottom / CELL); row += 1) {
          const key = `${column},${row}`
          const list = this.cells.get(key)
          if (list) list.push(rect)
          else this.cells.set(key, [rect])
        }
      }
    }
  }

  near(left: number, top: number, right: number, bottom: number): readonly Extent[] {
    const firstColumn = Math.floor(left / CELL)
    const lastColumn = Math.floor(right / CELL)
    const firstRow = Math.floor(top / CELL)
    const lastRow = Math.floor(bottom / CELL)
    if (firstColumn === lastColumn && firstRow === lastRow) return this.cells.get(`${firstColumn},${firstRow}`) ?? []
    const seen = new Set<Extent>()
    for (let column = firstColumn; column <= lastColumn; column += 1) {
      for (let row = firstRow; row <= lastRow; row += 1) {
        for (const rect of this.cells.get(`${column},${row}`) ?? []) seen.add(rect)
      }
    }
    return [...seen]
  }
}

const holds = (extent: Extent, point: Point): boolean =>
  extent.left <= point.x && point.x <= extent.right && extent.top <= point.y && point.y <= extent.bottom

/** Where one connector's route may go: a box it stays inside, boxes it crosses only one way. */
export interface Bounds {
  /** The smallest box holding both ends: the route stays inside it. */
  readonly within: Extent | null
  /** Boxes holding the target and not the source: once inside one, the route does not leave it. */
  readonly staysIn: readonly Extent[]
  /** Boxes holding the source and not the target: once outside one, the route does not come back. */
  readonly staysOut: readonly Extent[]
}

const UNBOUNDED: Bounds = { within: null, staysIn: [], staysOut: [] }

/** Whether the step from *a* to *b* leaves the route's bounds. */
const brokenBy = (bounds: Bounds, a: Point, b: Point): boolean => {
  if (bounds.within && !(holds(bounds.within, a) && holds(bounds.within, b))) return true
  return (
    bounds.staysIn.some((box) => holds(box, a) && !holds(box, b)) ||
    bounds.staysOut.some((box) => !holds(box, a) && holds(box, b))
  )
}

const bordersOf = (boxes: Iterable<Extent>): Lines => {
  const lines = new Lines()
  for (const box of boxes) {
    const corners: Point[] = [
      { x: box.left, y: box.top },
      { x: box.right, y: box.top },
      { x: box.right, y: box.bottom },
      { x: box.left, y: box.bottom },
    ]
    corners.forEach((corner, index) => lines.add(corner, corners[(index + 1) % 4]))
  }
  return lines
}

const cornersOf = (rect: Extent): Point[] => [
  { x: rect.left, y: rect.top },
  { x: rect.right, y: rect.top },
  { x: rect.left, y: rect.bottom },
  { x: rect.right, y: rect.bottom },
]

/** The graph's interesting points: the corners of every element and text region moved out by
 * BUFFER, and of every box border moved BORDER_OFFSET to either side. */
const interestingPoints = (scene: RoutingScene, grown: Iterable<Extent>): Point[] => {
  const points = [...grown].flatMap(cornersOf)
  for (const text of scene.text.values()) points.push(...cornersOf(grownOutward(text, BUFFER)))
  for (const box of scene.boxes.values()) {
    const xs = [
      Math.floor(box.left - BORDER_OFFSET),
      Math.ceil(box.left + BORDER_OFFSET),
      Math.floor(box.right - BORDER_OFFSET),
      Math.ceil(box.right + BORDER_OFFSET),
    ]
    const ys = [
      Math.floor(box.top - BORDER_OFFSET),
      Math.ceil(box.top + BORDER_OFFSET),
      Math.floor(box.bottom - BORDER_OFFSET),
      Math.ceil(box.bottom + BORDER_OFFSET),
    ]
    for (const x of xs) for (const y of ys) points.push({ x, y })
  }
  return points
}

export class Visibility {
  readonly grown: ReadonlyMap<string, Extent>
  readonly blocking: RectIndex
  readonly borders: Lines
  readonly graph: Graph

  constructor(readonly scene: RoutingScene) {
    this.grown = new Map([...scene.elements].map(([key, extent]) => [key, grownOutward(extent, BUFFER)]))
    this.blocking = new RectIndex([...this.grown.values(), ...scene.text.values()])
    this.borders = bordersOf(scene.boxes.values())
    const obstacles = [...this.grown.values(), ...scene.text.values()]
    this.graph = new Graph(obstacles, interestingPoints(scene, this.grown.values()))
  }

  /** What blocks the connector from ends[0] to ends[1]; with *bounded*, its bounds too. */
  passage(ends: readonly [string, string], bounded = true): Passage {
    const own = ends.map((end) => extentOf(this.scene, end))
    const walls = [...this.scene.boxes]
      .filter(([key, box]) => ends.includes(key) || !own.some((end) => encloses(box, end) && !sameExtent(box, end)))
      .map(([, box]) => box)
    return new Passage(this, walls, [], null, bounded ? this.bounds(ends) : UNBOUNDED)
  }

  /** The boxes the connector from ends[0] to ends[1] keeps to, and crosses once. */
  bounds(ends: readonly [string, string]): Bounds {
    const source = extentOf(this.scene, ends[0])
    const target = extentOf(this.scene, ends[1])
    const holding = [...this.scene.boxes].filter(
      ([key, box]) => !ends.includes(key) && !sameExtent(box, source) && !sameExtent(box, target),
    )
    let within: [number, string, Extent] | null = null
    for (const [key, box] of holding) {
      if (!encloses(box, source) || !encloses(box, target)) continue
      const area = (box.right - box.left) * (box.bottom - box.top)
      if (within === null || area < within[0] || (area === within[0] && byText(key, within[1]) < 0)) {
        within = [area, key, box]
      }
    }
    return {
      within: within === null ? null : within[2],
      staysIn: holding.filter(([, box]) => encloses(box, target) && !encloses(box, source)).map(([, box]) => box),
      staysOut: holding.filter(([, box]) => encloses(box, source) && !encloses(box, target)).map(([, box]) => box),
    }
  }
}

export class Passage {
  private readonly wallIndex: RectIndex

  constructor(
    private readonly visibility: Visibility,
    readonly walls: readonly Extent[],
    private readonly also: readonly Extent[] = [],
    private readonly crowd: Lines | null = null,
    readonly bounds: Bounds = UNBOUNDED,
    private readonly stubs: readonly [Stubs, string] | null = null,
  ) {
    this.wallIndex = new RectIndex([...walls, ...also])
  }

  /** This passage with *rects* blocking as well, *crowd* the routes found before it, and *stubs*
   * the stubs no run goes along but those of the connector named with them. */
  adding(rects: readonly Extent[], crowd: Lines | null = null, stubs: readonly [Stubs, string] | null = null): Passage {
    return new Passage(
      this.visibility,
      this.walls,
      [...this.also, ...rects],
      crowd ?? this.crowd,
      this.bounds,
      stubs ?? this.stubs,
    )
  }

  /** This passage without its bounds: for a connector no route within them reaches. */
  unbounded(): Passage {
    return new Passage(this.visibility, this.walls, this.also, this.crowd, UNBOUNDED, this.stubs)
  }

  crowding(a: Point, b: Point): number {
    if (!this.crowd || this.crowd.near(a, b, ROOM_LOOKED_FOR) === 0) return 0
    const [least, most] = this.roomAcross(a, b)
    const inChannel = this.crowd.between(a, b, least, most)
    const fits = Math.floor((most - least) / IDEAL_SEPARATION) + 1 - this.visibility.borders.between(a, b, least, most)
    return this.crowd.near(a, b, IDEAL_SEPARATION) + (inChannel + 1 > fits ? FULL : 0)
  }

  private roomAcross(a: Point, b: Point): [number, number] {
    const level = a.y === b.y
    const at = level ? a.y : a.x
    const low = level ? Math.min(a.x, b.x) : Math.min(a.y, b.y)
    const high = level ? Math.max(a.x, b.x) : Math.max(a.y, b.y)
    const reach = ROOM_LOOKED_FOR
    const near = level
      ? this.nearRects(low, at - reach, high, at + reach)
      : this.nearRects(at - reach, low, at + reach, high)
    let least = at - reach
    let most = at + reach
    for (const rect of near) {
      const rLow = level ? rect.left : rect.top
      const rHigh = level ? rect.right : rect.bottom
      const rNear = level ? rect.top : rect.left
      const rFar = level ? rect.bottom : rect.right
      if (Math.max(rLow, low) < Math.min(rHigh, high)) {
        if (rFar <= at) least = Math.max(least, rFar)
        else if (rNear >= at) most = Math.min(most, rNear)
      }
    }
    return [least, most]
  }

  private nearRects(left: number, top: number, right: number, bottom: number): readonly Extent[] {
    const blocking = this.visibility.blocking.near(left, top, right, bottom)
    return [...blocking, ...this.wallIndex.near(left, top, right, bottom)]
  }

  pointBlocked(point: Point): boolean {
    return this.nearRects(point.x, point.y, point.x, point.y).some(
      (rect) => rect.left < point.x && point.x < rect.right && rect.top < point.y && point.y < rect.bottom,
    )
  }

  stepBlocked(a: Point, b: Point, ignoring: readonly Extent[] = []): boolean {
    const near = this.nearRects(Math.min(a.x, b.x), Math.min(a.y, b.y), Math.max(a.x, b.x), Math.max(a.y, b.y))
    return (
      near.some((rect) => !ignoring.some((ignored) => sameExtent(ignored, rect)) && enters(rect, a, b)) ||
      this.visibility.borders.along(a, b) ||
      brokenBy(this.bounds, a, b) ||
      (this.stubs !== null && this.stubs[0].along(a, b, this.stubs[1]))
    )
  }
}
