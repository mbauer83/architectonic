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
import { BEND_PENALTY, CROWDING } from './scene'
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

/** f, order, node, direction, goal index (-1: an ordinary state; else finishing at that goal). */
type Entry = readonly [number, number, number, number, number]

/** A binary heap of entries ordered by estimate, then by the order they were made. */
class Frontier {
  private readonly items: Entry[] = []

  get size(): number {
    return this.items.length
  }

  private static before(one: Entry, other: Entry): boolean {
    return one[0] < other[0] || (one[0] === other[0] && one[1] < other[1])
  }

  push(entry: Entry): void {
    const items = this.items
    items.push(entry)
    let at = items.length - 1
    while (at > 0) {
      const parent = (at - 1) >> 1
      if (!Frontier.before(items[at], items[parent])) break
      ;[items[at], items[parent]] = [items[parent], items[at]]
      at = parent
    }
  }

  pop(): Entry {
    const items = this.items
    const top = items[0]
    const last = items.pop() as Entry
    if (items.length > 0) {
      items[0] = last
      let at = 0
      for (;;) {
        const left = 2 * at + 1
        const right = left + 1
        let smallest = at
        if (left < items.length && Frontier.before(items[left], items[smallest])) smallest = left
        if (right < items.length && Frontier.before(items[right], items[smallest])) smallest = right
        if (smallest === at) break
        ;[items[at], items[smallest]] = [items[smallest], items[at]]
        at = smallest
      }
    }
    return top
  }
}

const windowsOf = (terminals: readonly Terminal[]): (Extent | null)[] => {
  const left = Math.min(...terminals.map((terminal) => terminal.point.x))
  const top = Math.min(...terminals.map((terminal) => terminal.point.y))
  const right = Math.max(...terminals.map((terminal) => terminal.point.x))
  const bottom = Math.max(...terminals.map((terminal) => terminal.point.y))
  return [
    ...[WINDOW, 3 * WINDOW].map((reach) => ({
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

  // Where each step leads and what it costs; null where it is blocked or leaves the window.
  const steps = new Map<number, readonly [number, number] | null>()
  const step = (node: number, turn: number): readonly [number, number] | null => {
    const key = 4 * node + turn
    const known = steps.get(key)
    if (known !== undefined) return known
    let answer: readonly [number, number] | null = null
    const reached = graph.next(node, turn)
    if (reached >= 0) {
      const x = graph.x(reached)
      const y = graph.y(reached)
      const inside = window === null || (window.left <= x && x <= window.right && window.top <= y && y <= window.bottom)
      const here = { x: graph.x(node), y: graph.y(node) }
      const there = { x, y }
      if (inside && !passage.stepBlocked(here, there)) {
        const length = Math.abs(x - here.x) + Math.abs(y - here.y)
        answer = [reached, length * (1 + CROWDING * passage.crowding(here, there))]
      }
    }
    steps.set(key, answer)
    return answer
  }

  const best = new Map<number, number>()
  const came = new Map<number, number>()
  const began = new Map<number, number>()
  const frontier = new Frontier()
  let order = 0
  for (const start of starts) {
    const node = graph.nodeAt(start.point)
    const state = 4 * node + start.direction
    if (!best.has(state)) {
      best.set(state, 0)
      came.set(state, -1)
      began.set(state, start.tag)
      frontier.push([EAGERNESS * estimate(start.point.x, start.point.y), order, node, start.direction, -1])
      order += 1
    }
  }
  while (frontier.size > 0) {
    const [f, , node, last, finishing] = frontier.pop()
    const state = 4 * node + last
    if (finishing >= 0) {
      return { points: walkedBack(state, came, graph), start: began.get(state) ?? 0, goal: goals[finishing].tag, cost: f }
    }
    const g = best.get(state) ?? Number.POSITIVE_INFINITY
    if (f > g + EAGERNESS * estimate(graph.x(node), graph.y(node))) continue
    for (const index of goalsAt.get(node) ?? []) {
      if (last === REVERSE[goals[index].direction]) continue
      const finish = g + (last !== goals[index].direction ? BEND_PENALTY : 0)
      frontier.push([finish, order, node, last, index])
      order += 1
    }
    for (let turn = 0; turn < 4; turn += 1) {
      if (turn === REVERSE[last]) continue
      const taken = step(node, turn)
      if (taken === null) continue
      const [reached, length] = taken
      const then = 4 * reached + turn
      const cost = g + length + (turn !== last ? BEND_PENALTY : 0)
      if (cost < (best.get(then) ?? Number.POSITIVE_INFINITY)) {
        best.set(then, cost)
        came.set(then, state)
        began.set(then, began.get(state) ?? 0)
        frontier.push([cost + EAGERNESS * estimate(graph.x(reached), graph.y(reached)), order, reached, turn, -1])
        order += 1
      }
    }
  }
  return null
}

const walkedBack = (end: number, came: ReadonlyMap<number, number>, graph: Joined): Point[] => {
  const points: Point[] = []
  let state = end
  while (state >= 0) {
    const node = Math.floor(state / 4)
    points.push({ x: graph.x(node), y: graph.y(node) })
    state = came.get(state) ?? -1
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
