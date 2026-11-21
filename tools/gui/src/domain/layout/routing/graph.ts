/**
 * The orthogonal visibility graph itself (GD 2009 §3): segments of visibility, stopped by obstacles.
 *
 * The TypeScript mirror of `src/domain/diagrams/layout/routing/graph.py`. Through every interesting
 * point a level and an upright segment run as far as the first obstacle on either side lets them; a
 * node is where a level segment crosses an upright one, joined to the next node along either. A
 * search joins its terminals to the scene's graph without changing it.
 */
import type { Extent, Point } from '../geometry'

export const EAST = 0
export const WEST = 1
export const SOUTH = 2
export const NORTH = 3

/** A segment: the line it lies on, and where it starts and ends along that line. */
type Segment = readonly [number, number, number]

const pointKey = (x: number, y: number): string => `${x},${y}`

const byNumber = (one: number, other: number): number => one - other

const bySegment = (one: Segment, other: Segment): number =>
  one[0] - other[0] || one[1] - other[1] || one[2] - other[2]

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

const spanning = (obstacles: readonly Extent[], at: number, level: boolean): [number, number][] =>
  level
    ? obstacles.filter((rect) => rect.top < at && at < rect.bottom).map((rect) => [rect.left, rect.right])
    : obstacles.filter((rect) => rect.left < at && at < rect.right).map((rect) => [rect.top, rect.bottom])

/** The free stretch of a line about *along*, between the obstacles on it; null inside one. */
const free = (stretches: readonly (readonly [number, number])[], along: number): [number, number] | null => {
  let low = Number.NEGATIVE_INFINITY
  let high = Number.POSITIVE_INFINITY
  for (const [start, end] of stretches) {
    if (start < along && along < end) return null
    if (end <= along) low = Math.max(low, end)
    else if (start >= along) high = Math.min(high, start)
  }
  return [low, high]
}

const segmentsThrough = (points: readonly Point[], obstacles: readonly Extent[], level: boolean): Segment[] => {
  const alongLine = new Map<number, Set<number>>()
  for (const point of points) {
    const at = level ? point.y : point.x
    const set = alongLine.get(at) ?? new Set<number>()
    set.add(level ? point.x : point.y)
    alongLine.set(at, set)
  }
  const found = new Map<string, Segment>()
  for (const [at, alongs] of alongLine) {
    const stretches = spanning(obstacles, at, level)
    for (const along of alongs) {
      const stretch = free(stretches, along)
      if (stretch) found.set(`${at},${stretch[0]},${stretch[1]}`, [at, stretch[0], stretch[1]])
    }
  }
  return [...found.values()].sort(bySegment)
}

/** Segments in one orientation, found by their line and a position along it. */
class Segments {
  readonly onLine = new Map<number, number[]>()
  readonly lows = new Map<number, number[]>()
  readonly lines: number[]

  constructor(readonly segments: readonly Segment[]) {
    segments.forEach(([at, low], index) => {
      const on = this.onLine.get(at)
      if (on) {
        on.push(index)
        this.lows.get(at)?.push(low)
      } else {
        this.onLine.set(at, [index])
        this.lows.set(at, [low])
      }
    })
    this.lines = [...this.onLine.keys()].sort(byNumber)
  }

  /** The segment on the line *at* that holds *along*, or -1. */
  holding(at: number, along: number): number {
    const lows = this.lows.get(at)
    if (!lows) return -1
    const position = upperBound(lows, along) - 1
    if (position < 0) return -1
    const index = (this.onLine.get(at) as number[])[position]
    return along <= this.segments[index][2] ? index : -1
  }

  /** Each segment of the other orientation's lines from *low* to *high* that holds *at*. */
  *crossing(at: number, low: number, high: number): Generator<readonly [number, number]> {
    const last = upperBound(this.lines, high)
    for (let position = lowerBound(this.lines, low); position < last; position += 1) {
      const line = this.lines[position]
      const index = this.holding(line, at)
      if (index >= 0) yield [line, index]
    }
  }
}

/** The scene's orthogonal visibility graph: nodes, and each node's next node in each direction. */
export class Graph {
  readonly level: Segments
  readonly upright: Segments
  readonly xs: number[] = []
  readonly ys: number[] = []
  readonly at = new Map<string, number>()
  readonly levelNodes: number[][]
  readonly uprightNodes: number[][]
  readonly levelAlong: number[][]
  readonly uprightAlong: number[][]
  readonly next: Int32Array

  constructor(
    readonly obstacles: readonly Extent[],
    points: readonly Point[],
  ) {
    this.level = new Segments(segmentsThrough(points, obstacles, true))
    this.upright = new Segments(segmentsThrough(points, obstacles, false))
    this.levelNodes = this.level.segments.map(() => [])
    this.uprightNodes = this.upright.segments.map(() => [])
    this.level.segments.forEach(([y, low, high], index) => {
      for (const [x, upright] of this.upright.crossing(y, low, high)) {
        const node = this.xs.length
        this.xs.push(x)
        this.ys.push(y)
        this.at.set(pointKey(x, y), node)
        this.levelNodes[index].push(node)
        this.uprightNodes[upright].push(node)
      }
    })
    this.levelAlong = this.levelNodes.map((nodes) => nodes.map((node) => this.xs[node]))
    this.uprightAlong = this.uprightNodes.map((nodes) => nodes.map((node) => this.ys[node]))
    this.next = new Int32Array(4 * this.xs.length).fill(-1)
    for (const nodes of this.levelNodes) {
      for (let index = 1; index < nodes.length; index += 1) {
        this.next[4 * nodes[index - 1] + EAST] = nodes[index]
        this.next[4 * nodes[index] + WEST] = nodes[index - 1]
      }
    }
    for (const nodes of this.uprightNodes) {
      for (let index = 1; index < nodes.length; index += 1) {
        this.next[4 * nodes[index - 1] + SOUTH] = nodes[index]
        this.next[4 * nodes[index] + NORTH] = nodes[index - 1]
      }
    }
  }

  joined(points: readonly Point[]): Joined {
    return new Joined(this, points)
  }
}

const addTo = (map: Map<number, Map<string, Point>>, index: number, x: number, y: number): void => {
  const points = map.get(index) ?? new Map<string, Point>()
  points.set(pointKey(x, y), { x, y })
  map.set(index, points)
}

/** A scene's graph with one search's terminals joined to it, the scene's graph left as it was. */
export class Joined {
  private readonly base: number
  private readonly addedXs: number[] = []
  private readonly addedYs: number[] = []
  private readonly addedAt = new Map<string, number>()
  private readonly joins = new Map<number, number>()

  constructor(
    private readonly graph: Graph,
    points: readonly Point[],
  ) {
    this.base = graph.xs.length
    const unique = new Map(points.map((point) => [pointKey(point.x, point.y), point]))
    const own = [...unique.values()].sort((one, other) => one.x - other.x || one.y - other.y)
    const level = this.segmentsThrough(own, graph.level, true)
    const upright = this.segmentsThrough(own, graph.upright, false)
    const newLevel = level.filter(([index]) => index >= graph.level.segments.length)
    const newUpright = upright.filter(([index]) => index >= graph.upright.segments.length)
    const onLevel = new Map<number, Map<string, Point>>()
    const onUpright = new Map<number, Map<string, Point>>()
    for (const [index, [y, low, high]] of newLevel) {
      for (const [x, other] of graph.upright.crossing(y, low, high)) {
        addTo(onLevel, index, x, y)
        addTo(onUpright, other, x, y)
      }
      for (const [other, [x, otherLow, otherHigh]] of newUpright) {
        if (low <= x && x <= high && otherLow <= y && y <= otherHigh) {
          addTo(onLevel, index, x, y)
          addTo(onUpright, other, x, y)
        }
      }
    }
    for (const [index, [x, low, high]] of newUpright) {
      for (const [y, other] of graph.level.crossing(x, low, high)) {
        addTo(onUpright, index, x, y)
        addTo(onLevel, other, x, y)
      }
    }
    // Where a terminal's segment crosses another there is a node no scene segment had.
    const crossings = new Map<string, Point>()
    for (const pointsOn of onLevel.values()) for (const [key, point] of pointsOn) crossings.set(key, point)
    const added = [...crossings]
      .filter(([key]) => !graph.at.has(key))
      .map(([, point]) => point)
      .sort((one, other) => one.x - other.x || one.y - other.y)
    for (const point of added) {
      this.addedAt.set(pointKey(point.x, point.y), this.base + this.addedXs.length)
      this.addedXs.push(point.x)
      this.addedYs.push(point.y)
    }
    for (const [index, pointsOn] of [...onLevel].sort(([one], [other]) => one - other)) {
      const scene = index < graph.levelNodes.length
      this.link(scene ? graph.levelNodes[index] : [], scene ? graph.levelAlong[index] : [], pointsOn.values(), EAST, WEST, true)
    }
    for (const [index, pointsOn] of [...onUpright].sort(([one], [other]) => one - other)) {
      const scene = index < graph.uprightNodes.length
      this.link(scene ? graph.uprightNodes[index] : [], scene ? graph.uprightAlong[index] : [], pointsOn.values(), SOUTH, NORTH, false)
    }
  }

  private segmentsThrough(own: readonly Point[], segments: Segments, level: boolean): [number, Segment][] {
    const found = new Map<string, [number, Segment]>()
    let added = segments.segments.length
    for (const point of own) {
      const at = level ? point.y : point.x
      const along = level ? point.x : point.y
      const stretch = free(spanning(this.graph.obstacles, at, level), along)
      if (!stretch) continue
      const key = `${at},${stretch[0]},${stretch[1]}`
      if (found.has(key)) continue
      let index = segments.holding(at, along)
      if (index < 0) {
        index = added
        added += 1
      }
      found.set(key, [index, [at, stretch[0], stretch[1]]])
    }
    return [...found.values()].sort(([one], [other]) => one - other)
  }

  /** Joins, along one segment, each node the search added to its neighbours there. */
  private link(
    sceneNodes: readonly number[],
    sceneAlong: readonly number[],
    pointsOn: Iterable<Point>,
    forward: number,
    back: number,
    byX: boolean,
  ): void {
    const added: [number, number][] = []
    for (const point of pointsOn) {
      const node = this.nodeAt(point)
      if (node >= this.base) added.push([byX ? point.x : point.y, node])
    }
    added.sort(([one], [other]) => one - other)
    const places = added.map(([along]) => lowerBound(sceneAlong, along))
    added.forEach(([, node], index) => {
      const place = places[index]
      const before =
        index > 0 && places[index - 1] === place ? added[index - 1][1] : place > 0 ? sceneNodes[place - 1] : -1
      const after =
        index + 1 < added.length && places[index + 1] === place
          ? added[index + 1][1]
          : place < sceneNodes.length
            ? sceneNodes[place]
            : -1
      if (before >= 0) {
        this.joins.set(4 * node + back, before)
        this.joins.set(4 * before + forward, node)
      }
      if (after >= 0) {
        this.joins.set(4 * node + forward, after)
        this.joins.set(4 * after + back, node)
      }
    })
  }

  nodeAt(point: Point): number {
    const key = pointKey(point.x, point.y)
    const node = this.graph.at.get(key) ?? this.addedAt.get(key)
    if (node === undefined) throw new Error(`no node at ${key}`)
    return node
  }

  x(node: number): number {
    return node < this.base ? this.graph.xs[node] : this.addedXs[node - this.base]
  }

  y(node: number): number {
    return node < this.base ? this.graph.ys[node] : this.addedYs[node - this.base]
  }

  /** The next node from *node* in *direction*, or -1. */
  next(node: number, direction: number): number {
    const key = 4 * node + direction
    const joined = this.joins.get(key)
    if (joined !== undefined) return joined
    return node < this.base ? this.graph.next[key] : -1
  }

  /** Every node, the scene's and the search's. */
  get size(): number {
    return this.base + this.addedXs.length
  }
}
