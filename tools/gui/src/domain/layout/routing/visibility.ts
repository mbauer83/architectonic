/**
 * The orthogonal visibility graph's lines, and what blocks a step along one of them.
 *
 * The TypeScript mirror of `src/domain/diagrams/layout/routing/visibility.py`: candidate lines at
 * every element's edges moved out by BUFFER, every text region's likewise, every box border moved
 * BORDER_OFFSET either side, all whole numbers. For one connector, an element (grown), a text region
 * and a wall — a box holding neither of its ends, or one that is an end — block; a run along any
 * box border closer than the clearance blocks too.
 */
import type { Extent, Point } from '../geometry'
import { encloses } from '../geometry'
import { LINE_CLEARANCE } from '../routeQuality'
import type { RoutingScene } from './scene'
import { BORDER_OFFSET, BUFFER, IDEAL_SEPARATION, extentOf, sameExtent } from './scene'

const CELL = 128
const SHARED = 1
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

  near(left: number, top: number, right: number, bottom: number): Extent[] {
    const seen = new Set<Extent>()
    for (let column = Math.floor(left / CELL); column <= Math.floor(right / CELL); column += 1) {
      for (let row = Math.floor(top / CELL); row <= Math.floor(bottom / CELL); row += 1) {
        for (const rect of this.cells.get(`${column},${row}`) ?? []) seen.add(rect)
      }
    }
    return [...seen]
  }
}

const lowerBound = (sorted: readonly number[], value: number): number => {
  let low = 0
  let high = sorted.length
  while (low < high) {
    const middle = (low + high) >> 1
    if (sorted[middle] < value) low = middle + 1
    else high = middle
  }
  return low
}

const upperBound = (sorted: readonly number[], value: number): number => {
  let low = 0
  let high = sorted.length
  while (low < high) {
    const middle = (low + high) >> 1
    if (sorted[middle] <= value) low = middle + 1
    else high = middle
  }
  return low
}

const insertSorted = (sorted: number[], value: number): void => {
  sorted.splice(upperBound(sorted, value), 0, value)
}

/** Spans along lines, level ones by their y and upright ones by their x. */
export class Lines {
  private readonly level = new Map<number, [number, number][]>()
  private readonly upright = new Map<number, [number, number][]>()
  private readonly levelAt: number[] = []
  private readonly uprightAt: number[] = []

  add(a: Point, b: Point): void {
    if (a.y === b.y && a.x !== b.x) {
      if (!this.level.has(a.y)) {
        insertSorted(this.levelAt, a.y)
        this.level.set(a.y, [])
      }
      this.level.get(a.y)?.push([Math.min(a.x, b.x), Math.max(a.x, b.x)])
    } else if (a.x === b.x && a.y !== b.y) {
      if (!this.upright.has(a.x)) {
        insertSorted(this.uprightAt, a.x)
        this.upright.set(a.x, [])
      }
      this.upright.get(a.x)?.push([Math.min(a.y, b.y), Math.max(a.y, b.y)])
    }
  }

  near(a: Point, b: Point, within: number): number {
    const isLevel = a.y === b.y
    const at = isLevel ? a.y : a.x
    const low = isLevel ? Math.min(a.x, b.x) : Math.min(a.y, b.y)
    const high = isLevel ? Math.max(a.x, b.x) : Math.max(a.y, b.y)
    const positions = isLevel ? this.levelAt : this.uprightAt
    const spans = isLevel ? this.level : this.upright
    const first = lowerBound(positions, at - within + 1e-9)
    const last = upperBound(positions, at + within - 1e-9)
    let count = 0
    for (const position of positions.slice(first, last)) {
      for (const [spanLow, spanHigh] of spans.get(position) ?? []) {
        if (Math.min(high, spanHigh) - Math.max(low, spanLow) > SHARED) count += 1
      }
    }
    return count
  }

  between(a: Point, b: Point, least: number, most: number): number {
    const isLevel = a.y === b.y
    const low = isLevel ? Math.min(a.x, b.x) : Math.min(a.y, b.y)
    const high = isLevel ? Math.max(a.x, b.x) : Math.max(a.y, b.y)
    const positions = isLevel ? this.levelAt : this.uprightAt
    const spans = isLevel ? this.level : this.upright
    let count = 0
    for (const position of positions.slice(lowerBound(positions, least), upperBound(positions, most))) {
      for (const [spanLow, spanHigh] of spans.get(position) ?? []) {
        if (Math.min(high, spanHigh) - Math.max(low, spanLow) > SHARED) count += 1
      }
    }
    return count
  }

  along(a: Point, b: Point): boolean {
    return this.near(a, b, LINE_CLEARANCE) > 0
  }
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

export class Visibility {
  readonly grown: ReadonlyMap<string, Extent>
  readonly blocking: RectIndex
  readonly borders: Lines
  readonly xs: number[]
  readonly ys: number[]

  constructor(readonly scene: RoutingScene) {
    this.grown = new Map([...scene.elements].map(([key, extent]) => [key, grownOutward(extent, BUFFER)]))
    this.blocking = new RectIndex([...this.grown.values(), ...scene.text.values()])
    this.borders = bordersOf(scene.boxes.values())
    const xs = new Set<number>()
    const ys = new Set<number>()
    for (const rect of [...this.grown.values(), ...[...scene.text.values()].map((text) => grownOutward(text, BUFFER))]) {
      xs.add(rect.left).add(rect.right)
      ys.add(rect.top).add(rect.bottom)
    }
    for (const box of scene.boxes.values()) {
      xs.add(Math.floor(box.left - BORDER_OFFSET)).add(Math.ceil(box.left + BORDER_OFFSET))
      xs.add(Math.floor(box.right - BORDER_OFFSET)).add(Math.ceil(box.right + BORDER_OFFSET))
      ys.add(Math.floor(box.top - BORDER_OFFSET)).add(Math.ceil(box.top + BORDER_OFFSET))
      ys.add(Math.floor(box.bottom - BORDER_OFFSET)).add(Math.ceil(box.bottom + BORDER_OFFSET))
    }
    this.xs = [...xs].sort((one, other) => one - other)
    this.ys = [...ys].sort((one, other) => one - other)
  }

  passage(ends: readonly [string, string]): Passage {
    const own = ends.map((end) => extentOf(this.scene, end))
    const walls = [...this.scene.boxes]
      .filter(([key, box]) => ends.includes(key) || !own.some((end) => encloses(box, end) && !sameExtent(box, end)))
      .map(([, box]) => box)
    return new Passage(this, walls)
  }
}

export class Passage {
  private readonly wallIndex: RectIndex

  constructor(
    private readonly visibility: Visibility,
    readonly walls: readonly Extent[],
    private readonly also: readonly Extent[] = [],
    private readonly crowd: Lines | null = null,
  ) {
    this.wallIndex = new RectIndex([...walls, ...also])
  }

  adding(rects: readonly Extent[], crowd: Lines | null = null): Passage {
    return new Passage(this.visibility, this.walls, [...this.also, ...rects], crowd ?? this.crowd)
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

  private nearRects(left: number, top: number, right: number, bottom: number): Extent[] {
    return [...this.visibility.blocking.near(left, top, right, bottom), ...this.wallIndex.near(left, top, right, bottom)]
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
      this.visibility.borders.along(a, b)
    )
  }
}

/** The candidate lines between *low* and *high*, with *extra* added. */
export const linesWithin = (lines: readonly number[], low: number, high: number, extra: Iterable<number>): number[] =>
  [...new Set([...lines.slice(lowerBound(lines, low), upperBound(lines, high)), ...extra])].sort(
    (one, other) => one - other,
  )
