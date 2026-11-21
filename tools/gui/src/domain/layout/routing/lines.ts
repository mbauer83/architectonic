/**
 * Spans along lines, asked what lies near a run: the routes found so far, box borders, stubs.
 *
 * The TypeScript mirror of `src/domain/diagrams/layout/routing/lines.py`.
 */
import type { Point } from '../geometry'
import { LINE_CLEARANCE } from '../routeQuality'

const SHARED = 1

export const lowerBound = (sorted: readonly number[], value: number): number => {
  let low = 0
  let high = sorted.length
  while (low < high) {
    const middle = (low + high) >> 1
    if (sorted[middle] < value) low = middle + 1
    else high = middle
  }
  return low
}

export const upperBound = (sorted: readonly number[], value: number): number => {
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
    const positions = isLevel ? this.levelAt : this.uprightAt
    const [low, high] = [lowerBound(positions, at - within + 1e-9), upperBound(positions, at + within - 1e-9)]
    return this.sharing(a, b, positions, low, high)
  }

  between(a: Point, b: Point, least: number, most: number): number {
    const positions = a.y === b.y ? this.levelAt : this.uprightAt
    return this.sharing(a, b, positions, lowerBound(positions, least), upperBound(positions, most))
  }

  /** How many spans on the lines at positions[first..last) share more than SHARED of the run a–b's stretch. */
  private sharing(a: Point, b: Point, positions: readonly number[], first: number, last: number): number {
    const isLevel = a.y === b.y
    const low = isLevel ? Math.min(a.x, b.x) : Math.min(a.y, b.y)
    const high = isLevel ? Math.max(a.x, b.x) : Math.max(a.y, b.y)
    const spans = isLevel ? this.level : this.upright
    let count = 0
    for (let position = first; position < last; position += 1) {
      for (const [spanLow, spanHigh] of spans.get(positions[position]) ?? []) {
        if ((high < spanHigh ? high : spanHigh) - (low > spanLow ? low : spanLow) > SHARED) count += 1
      }
    }
    return count
  }

  along(a: Point, b: Point): boolean {
    return this.near(a, b, LINE_CLEARANCE) > 0
  }

  /** The spans on lines closer than *within* to the run a–b's, as [line, low, high]. */
  spansNear(a: Point, b: Point, within: number): [number, number, number][] {
    const isLevel = a.y === b.y
    const at = isLevel ? a.y : a.x
    const positions = isLevel ? this.levelAt : this.uprightAt
    const spans = isLevel ? this.level : this.upright
    const found: [number, number, number][] = []
    const last = upperBound(positions, at + within - 1e-9)
    for (let position = lowerBound(positions, at - within + 1e-9); position < last; position += 1) {
      const line = positions[position]
      for (const [low, high] of spans.get(line) ?? []) found.push([line, low, high])
    }
    return found
  }
}

/** Every connector's stubs, by connector: a run goes along none but its own connector's. */
export class Stubs {
  private readonly lines = new Lines()
  private readonly owners = new Map<string, Set<string>>()

  add(a: Point, b: Point, owner: string): void {
    this.lines.add(a, b)
    const level = a.y === b.y
    const key = level
      ? `${level},${a.y},${Math.min(a.x, b.x)},${Math.max(a.x, b.x)}`
      : `${level},${a.x},${Math.min(a.y, b.y)},${Math.max(a.y, b.y)}`
    const owners = this.owners.get(key) ?? new Set<string>()
    owners.add(owner)
    this.owners.set(key, owners)
  }

  /** Whether the run a–b goes along a stub of a connector other than *owner*'s. */
  along(a: Point, b: Point, owner: string): boolean {
    const level = a.y === b.y
    const low = level ? Math.min(a.x, b.x) : Math.min(a.y, b.y)
    const high = level ? Math.max(a.x, b.x) : Math.max(a.y, b.y)
    return this.lines.spansNear(a, b, LINE_CLEARANCE).some(
      ([line, spanLow, spanHigh]) =>
        Math.min(high, spanHigh) - Math.max(low, spanLow) > SHARED &&
        [...(this.owners.get(`${level},${line},${spanLow},${spanHigh}`) ?? [])].some((one) => one !== owner),
    )
  }
}
