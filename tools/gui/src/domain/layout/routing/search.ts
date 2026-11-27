/**
 * A* over the visibility graph, from any of a connector's starts to any of its goals (GD 2009 §4).
 *
 * The TypeScript mirror of `src/domain/diagrams/layout/routing/search.py`. States are (node,
 * direction); a step costs its length — more where routes found before run alongside — and
 * BEND_PENALTY where it turns. Entries leave the queue in order of estimate and then of when they
 * were made, which is what makes the route found the same in both languages.
 */
import type { Extent, Point } from '../geometry'
import type { Graph, Joined } from './graph'
import { BEND_PENALTY, CHANNEL_FULL, CROWDING } from './scene'
import type { Passage } from './visibility'
import { FULL } from './visibility'

/** East, west, south, north, as steps. */
export const DIRECTIONS: readonly (readonly [number, number])[] = [
  [1, 0],
  [-1, 0],
  [0, 1],
  [0, -1],
]

export const REVERSE: readonly number[] = [1, 0, 3, 2]

export const WINDOW = 200

/** How far beyond its terminals a far-reaching search first looks, as a share of how far apart they are. */
export const SPAN_SHARE = 0.1

/** How much the distance still to go is over-weighted: a promising way rather than the very cheapest. */
export const EAGERNESS = 1.5

export interface Terminal {
  readonly point: Point
  readonly direction: number
  readonly tag: number
}

export interface Found {
  readonly points: readonly Point[]
  readonly start: number
  readonly goal: number
  readonly cost: number
}

/**
 * A binary heap of entries ordered by estimate, then by the order they were made. An entry is five
 * numbers, held in typed arrays rather than as an object each: a search across a large picture pops
 * millions of them. Orders are unique, so the entries leave in the one order whatever the heap's shape.
 */
class Frontier {
  size = 0
  private estimates = new Float64Array(1024)
  private orders = new Float64Array(1024)
  private nodes = new Int32Array(1024)
  private directions = new Int32Array(1024)
  private goals = new Int32Array(1024)
  /** The entry `pop` took off last: its estimate, node, direction, and goal index (-1: an ordinary state). */
  estimate = 0
  node = 0
  direction = 0
  goal = -1

  clear(): void {
    this.size = 0
  }

  push(f: number, order: number, node: number, direction: number, goal: number): void {
    if (this.size === this.estimates.length) this.grow()
    const [estimates, orders] = [this.estimates, this.orders]
    let at = this.size
    this.size += 1
    while (at > 0) {
      const parent = (at - 1) >> 1
      if (!(f < estimates[parent] || (f === estimates[parent] && order < orders[parent]))) break
      this.move(at, parent)
      at = parent
    }
    this.put(at, f, order, node, direction, goal)
  }

  /** Takes the first entry off, into `estimate`, `node`, `direction` and `goal`. */
  pop(): void {
    const [estimates, orders] = [this.estimates, this.orders]
    this.estimate = estimates[0]
    this.node = this.nodes[0]
    this.direction = this.directions[0]
    this.goal = this.goals[0]
    this.size -= 1
    const last = this.size
    if (last === 0) return
    const [f, order] = [estimates[last], orders[last]]
    let at = 0
    for (;;) {
      let child = 2 * at + 1
      if (child >= last) break
      const right = child + 1
      if (right < last && (estimates[right] < estimates[child] ||
        (estimates[right] === estimates[child] && orders[right] < orders[child]))) child = right
      if (!(estimates[child] < f || (estimates[child] === f && orders[child] < order))) break
      this.move(at, child)
      at = child
    }
    this.move(at, last)
  }

  private put(at: number, f: number, order: number, node: number, direction: number, goal: number): void {
    this.estimates[at] = f
    this.orders[at] = order
    this.nodes[at] = node
    this.directions[at] = direction
    this.goals[at] = goal
  }

  private move(to: number, from: number): void {
    this.put(to, this.estimates[from], this.orders[from], this.nodes[from], this.directions[from], this.goals[from])
  }

  private grow(): void {
    const length = 2 * this.estimates.length
    const estimates = new Float64Array(length)
    const orders = new Float64Array(length)
    const nodes = new Int32Array(length)
    const directions = new Int32Array(length)
    const goals = new Int32Array(length)
    estimates.set(this.estimates)
    orders.set(this.orders)
    nodes.set(this.nodes)
    directions.set(this.directions)
    goals.set(this.goals)
    Object.assign(this, { estimates, orders, nodes, directions, goals })
  }
}

/**
 * What a search knows of each state (4 × node + direction), kept from one search to the next so a
 * search does not allocate and clear arrays the size of the graph. A state's entry counts only while it
 * carries the current stamp: the window's for the cheapest way found to it, the search's for its step.
 */
class Known {
  private states = 0
  private window = 0
  private search = 0
  /** Stamped by the window: the cheapest cost found to the state, the state it was reached from, its start's tag. */
  private reachedIn = new Int32Array(0)
  best = new Float64Array(0)
  came = new Int32Array(0)
  began = new Float64Array(0)
  /** Stamped by the search: where the step from the state leads (-1: blocked, or no node) and what it costs. */
  private steppedIn = new Int32Array(0)
  stepTo = new Int32Array(0)
  stepCost = new Float64Array(0)

  /** A new search over *states* states: no step known. */
  beginSearch(states: number): void {
    if (states > this.states) {
      this.states = Math.max(states, 2 * this.states)
      this.reachedIn = new Int32Array(this.states)
      this.best = new Float64Array(this.states)
      this.came = new Int32Array(this.states)
      this.began = new Float64Array(this.states)
      this.steppedIn = new Int32Array(this.states)
      this.stepTo = new Int32Array(this.states)
      this.stepCost = new Float64Array(this.states)
      this.window = 0
      this.search = 0
    }
    this.search = this.restamped(this.search, this.steppedIn)
  }

  /** A new window of the search: no state reached. */
  beginWindow(): void {
    this.window = this.restamped(this.window, this.reachedIn)
  }

  reached(state: number): boolean {
    return this.reachedIn[state] === this.window
  }

  /** The cheapest cost found to *state* in this window, or infinity. */
  cost(state: number): number {
    return this.reachedIn[state] === this.window ? this.best[state] : Number.POSITIVE_INFINITY
  }

  reach(state: number, cost: number, from: number, tag: number): void {
    this.reachedIn[state] = this.window
    this.best[state] = cost
    this.came[state] = from
    this.began[state] = tag
  }

  stepped(state: number): boolean {
    return this.steppedIn[state] === this.search
  }

  step(state: number, to: number, cost: number): void {
    this.steppedIn[state] = this.search
    this.stepTo[state] = to
    this.stepCost[state] = cost
  }

  private restamped(stamp: number, stamps: Int32Array): number {
    if (stamp < 0x7fffffff) return stamp + 1
    stamps.fill(0)
    return 1
  }
}

const FRONTIER = new Frontier()
const KNOWN = new Known()

/**
 * What a step costs: its length, a share more for each route already alongside, and a fixed sum where
 * its channel is full — so neither buys a detour longer than that.
 */
export const stepCost = (length: number, crowding: number): number => {
  const full = crowding >= FULL
  const alongside = full ? crowding - FULL : crowding
  return length * (1 + CROWDING * alongside) + (full ? CHANNEL_FULL : 0)
}

const windowsOf = (terminals: readonly Terminal[]): (Extent | null)[] => {
  const left = Math.min(...terminals.map((terminal) => terminal.point.x))
  const top = Math.min(...terminals.map((terminal) => terminal.point.y))
  const right = Math.max(...terminals.map((terminal) => terminal.point.x))
  const bottom = Math.max(...terminals.map((terminal) => terminal.point.y))
  const first = Math.max(WINDOW, SPAN_SHARE * Math.max(right - left, bottom - top))
  return [
    ...[first, 3 * first].map((reach) => ({
      left: left - reach,
      top: top - reach,
      right: right + reach,
      bottom: bottom + reach,
    })),
    null,
  ]
}

export const withoutStraightPoints = (points: readonly Point[]): Point[] => {
  const kept = [points[0]]
  for (let index = 1; index < points.length - 1; index += 1) {
    const before = kept[kept.length - 1]
    const here = points[index]
    const after = points[index + 1]
    const upright = before.x === here.x && here.x === after.x
    const level = before.y === here.y && here.y === after.y
    if (!upright && !level) kept.push(here)
  }
  return points.length > 1 ? [...kept, points[points.length - 1]] : kept
}

const searchWithin = (
  starts: readonly Terminal[],
  goals: readonly Terminal[],
  passage: Passage,
  graph: Joined,
  window: Extent | null,
): Found | null => {
  const known = KNOWN
  known.beginWindow()
  const goalsAt = new Map<number, number[]>()
  goals.forEach((goal, index) => {
    const node = graph.nodeAt(goal.point)
    const list = goalsAt.get(node)
    if (list) list.push(index)
    else goalsAt.set(node, [index])
  })
  const estimate = (x: number, y: number): number => {
    let least = Number.POSITIVE_INFINITY
    for (const goal of goals) least = Math.min(least, Math.abs(goal.point.x - x) + Math.abs(goal.point.y - y))
    return least
  }

  // Where each step leads and what it costs, asked once per search whatever its window (`known`); -1
  // where it is blocked, or leaves this window.
  const step = (node: number, turn: number): number => {
    const key = 4 * node + turn
    if (!known.stepped(key)) {
      let [to, cost] = [-1, 0]
      const reached = graph.next(node, turn)
      if (reached >= 0) {
        const here = { x: graph.x(node), y: graph.y(node) }
        const there = { x: graph.x(reached), y: graph.y(reached) }
        if (!passage.stepBlocked(here, there)) {
          const length = Math.abs(there.x - here.x) + Math.abs(there.y - here.y)
          ;[to, cost] = [reached, stepCost(length, passage.crowding(here, there))]
        }
      }
      known.step(key, to, cost)
    }
    const to = known.stepTo[key]
    if (to < 0 || window === null) return to
    const [x, y] = [graph.x(to), graph.y(to)]
    return window.left <= x && x <= window.right && window.top <= y && y <= window.bottom ? to : -1
  }

  const frontier = FRONTIER
  frontier.clear()
  let order = 0
  for (const start of starts) {
    const node = graph.nodeAt(start.point)
    const state = 4 * node + start.direction
    if (!known.reached(state)) {
      known.reach(state, 0, -1, start.tag)
      frontier.push(EAGERNESS * estimate(start.point.x, start.point.y), order, node, start.direction, -1)
      order += 1
    }
  }
  while (frontier.size > 0) {
    frontier.pop()
    const [f, node, last, finishing] = [frontier.estimate, frontier.node, frontier.direction, frontier.goal]
    const state = 4 * node + last
    if (finishing >= 0) {
      const points = walkedBack(state, known.came, graph)
      return { points, start: known.began[state], goal: goals[finishing].tag, cost: f }
    }
    const g = known.cost(state)
    if (f > g + EAGERNESS * estimate(graph.x(node), graph.y(node))) continue
    for (const index of goalsAt.get(node) ?? []) {
      if (last === REVERSE[goals[index].direction]) continue
      const finish = g + (last !== goals[index].direction ? BEND_PENALTY : 0)
      frontier.push(finish, order, node, last, index)
      order += 1
    }
    for (let turn = 0; turn < 4; turn += 1) {
      if (turn === REVERSE[last]) continue
      const reached = step(node, turn)
      if (reached < 0) continue
      const then = 4 * reached + turn
      const cost = g + known.stepCost[4 * node + turn] + (turn !== last ? BEND_PENALTY : 0)
      if (cost < known.cost(then)) {
        known.reach(then, cost, state, known.began[state])
        frontier.push(cost + EAGERNESS * estimate(graph.x(reached), graph.y(reached)), order, reached, turn, -1)
        order += 1
      }
    }
  }
  return null
}

const walkedBack = (end: number, came: Int32Array, graph: Joined): Point[] => {
  const points: Point[] = []
  let state = end
  while (state >= 0) {
    const node = Math.floor(state / 4)
    points.push({ x: graph.x(node), y: graph.y(node) })
    state = came[state]
  }
  return withoutStraightPoints(points.reverse())
}

/** The cheapest route from any start to any goal over *graph*, or null. */
export const search = (
  starts: readonly Terminal[],
  goals: readonly Terminal[],
  passage: Passage,
  graph: Graph,
): Found | null => {
  const terminals = [...starts, ...goals]
  const joined = graph.joined(terminals.map((terminal) => terminal.point))
  // What each step costs does not depend on the window: a wider window asks again only the steps it adds.
  KNOWN.beginSearch(4 * joined.size)
  let best: Found | null = null
  for (const window of windowsOf(terminals)) {
    if (window === null && best !== null) break
    const found = searchWithin(starts, goals, passage, joined, window)
    if (found && (best === null || found.cost < best.cost)) best = found
    if (best && !throughAFullChannel(best.points, passage)) return best
  }
  return best
}

const throughAFullChannel = (points: readonly Point[], passage: Passage): boolean =>
  points.slice(1).some((b, index) => passage.crowding(points[index], b) >= FULL)
