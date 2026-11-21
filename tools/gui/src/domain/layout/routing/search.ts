/**
 * A* over the visibility graph, from any of a connector's starts to any of its goals (GD 2009 §4).
 *
 * The TypeScript mirror of `src/domain/diagrams/layout/routing/search.py`. States are (node,
 * direction); a step costs its length — more where routes found before run alongside — and
 * BEND_PENALTY where it turns. Entries leave the queue in order of estimate and then of when they
 * were made, which is what makes the route found the same in both languages.
 */
import type { Extent, Point } from '../geometry'
import { BEND_PENALTY, CROWDING } from './scene'
import type { Passage } from './visibility'
import { FULL, linesWithin } from './visibility'

/** East, west, south, north, as steps along the grid. */
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

type Entry = readonly [number, number, number, number, number, number]

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

const stateKey = (i: number, j: number, direction: number): string => `${i},${j},${direction}`

const searchWithin = (
  starts: readonly Terminal[],
  goals: readonly Terminal[],
  passage: Passage,
  xs: readonly number[],
  ys: readonly number[],
): Found | null => {
  const column = new Map(xs.map((x, index) => [x, index]))
  const row = new Map(ys.map((y, index) => [y, index]))
  const indexOf = (map: ReadonlyMap<number, number>, value: number): number => {
    const found = map.get(value)
    if (found === undefined) throw new Error(`no line at ${value}`)
    return found
  }
  const goalsAt = new Map<string, number[]>()
  goals.forEach((goal, index) => {
    const key = `${indexOf(column, goal.point.x)},${indexOf(row, goal.point.y)}`
    const list = goalsAt.get(key)
    if (list) list.push(index)
    else goalsAt.set(key, [index])
  })
  const estimate = (x: number, y: number): number =>
    Math.min(...goals.map((goal) => Math.abs(goal.point.x - x) + Math.abs(goal.point.y - y)))

  const steps = new Map<string, number | null>()
  const stepCost = (i: number, j: number, turn: number): number | null => {
    const key = stateKey(i, j, turn)
    const known = steps.get(key)
    if (known !== undefined) return known
    const nextI = i + DIRECTIONS[turn][0]
    const nextJ = j + DIRECTIONS[turn][1]
    let answer: number | null = null
    if (nextI >= 0 && nextI < xs.length && nextJ >= 0 && nextJ < ys.length) {
      const here = { x: xs[i], y: ys[j] }
      const there = { x: xs[nextI], y: ys[nextJ] }
      if (!passage.pointBlocked(there) && !passage.stepBlocked(here, there)) {
        const length = Math.abs(there.x - here.x) + Math.abs(there.y - here.y)
        answer = length * (1 + CROWDING * passage.crowding(here, there))
      }
    }
    steps.set(key, answer)
    return answer
  }

  const best = new Map<string, number>()
  const came = new Map<string, readonly [number, number, number] | null>()
  const began = new Map<string, number>()
  const frontier = new Frontier()
  let order = 0
  for (const start of starts) {
    const i = indexOf(column, start.point.x)
    const j = indexOf(row, start.point.y)
    const key = stateKey(i, j, start.direction)
    if (!best.has(key)) {
      best.set(key, 0)
      came.set(key, null)
      began.set(key, start.tag)
      frontier.push([EAGERNESS * estimate(start.point.x, start.point.y), order, i, j, start.direction, -1])
      order += 1
    }
  }
  while (frontier.size > 0) {
    const [f, , i, j, last, finishing] = frontier.pop()
    const key = stateKey(i, j, last)
    if (finishing >= 0) {
      return { points: walkedBack([i, j, last], came, xs, ys), start: began.get(key) ?? 0, goal: goals[finishing].tag, cost: f }
    }
    const g = best.get(key) ?? Number.POSITIVE_INFINITY
    if (f > g + EAGERNESS * estimate(xs[i], ys[j])) continue
    for (const index of goalsAt.get(`${i},${j}`) ?? []) {
      if (last === REVERSE[goals[index].direction]) continue
      const finish = g + (last !== goals[index].direction ? BEND_PENALTY : 0)
      frontier.push([finish, order, i, j, last, index])
      order += 1
    }
    for (let turn = 0; turn < 4; turn += 1) {
      if (turn === REVERSE[last]) continue
      const length = stepCost(i, j, turn)
      if (length === null) continue
      const nextI = i + DIRECTIONS[turn][0]
      const nextJ = j + DIRECTIONS[turn][1]
      const there = { x: xs[nextI], y: ys[nextJ] }
      const reachedKey = stateKey(nextI, nextJ, turn)
      const cost = g + length + (turn !== last ? BEND_PENALTY : 0)
      if (cost < (best.get(reachedKey) ?? Number.POSITIVE_INFINITY)) {
        best.set(reachedKey, cost)
        came.set(reachedKey, [i, j, last])
        began.set(reachedKey, began.get(key) ?? 0)
        frontier.push([cost + EAGERNESS * estimate(there.x, there.y), order, nextI, nextJ, turn, -1])
        order += 1
      }
    }
  }
  return null
}

const walkedBack = (
  end: readonly [number, number, number],
  came: ReadonlyMap<string, readonly [number, number, number] | null>,
  xs: readonly number[],
  ys: readonly number[],
): Point[] => {
  const points: Point[] = []
  let state: readonly [number, number, number] | null = end
  while (state !== null) {
    points.push({ x: xs[state[0]], y: ys[state[1]] })
    state = came.get(stateKey(state[0], state[1], state[2])) ?? null
  }
  return withoutStraightPoints(points.reverse())
}

/** The cheapest route from any start to any goal over the lines *xs* and *ys*, or null. */
export const search = (
  starts: readonly Terminal[],
  goals: readonly Terminal[],
  passage: Passage,
  xs: readonly number[],
  ys: readonly number[],
): Found | null => {
  const terminals = [...starts, ...goals]
  let best: Found | null = null
  for (const window of windowsOf(terminals)) {
    if (window === null && best !== null) break
    const found = searchWithin(
      starts,
      goals,
      passage,
      linesWithin(xs, window ? window.left : Number.NEGATIVE_INFINITY, window ? window.right : Number.POSITIVE_INFINITY, terminals.map((terminal) => terminal.point.x)),
      linesWithin(ys, window ? window.top : Number.NEGATIVE_INFINITY, window ? window.bottom : Number.POSITIVE_INFINITY, terminals.map((terminal) => terminal.point.y)),
    )
    if (found && (best === null || found.cost < best.cost)) best = found
    if (best && !throughAFullChannel(best.points, passage)) return best
  }
  return best
}

const throughAFullChannel = (points: readonly Point[], passage: Passage): boolean =>
  points.slice(1).some((b, index) => passage.crowding(points[index], b) >= FULL)
