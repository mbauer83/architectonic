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

/** How wide a cell of `Cells` is across its lines, and along them. */
const CELL_ACROSS = 64
const CELL_ALONG = 256
/** Offsets a cell's place by, so the places of a picture's cells, negative or not, make one number. */
const CELL_SPREAD = 1 << 20

/**
 * Spans of one orientation filed in cells of their line and stretch, so a run is compared only with the
 * spans in the cells it reaches, not with every span on every line near it. A span is filed in every
 * cell its stretch passes through, and is counted against a run only in the cell where the stretch they
 * share begins, so it is counted once.
 */
class Cells {
  private readonly cells = new Map<number, { at: number[]; low: number[]; high: number[] }>()

  add(at: number, low: number, high: number): void {
    const across = Math.floor(at / CELL_ACROSS)
    for (let along = Math.floor(low / CELL_ALONG); along <= Math.floor(high / CELL_ALONG); along += 1) {
      const key = across * CELL_SPREAD + along
      const cell = this.cells.get(key)
      if (cell) {
        cell.at.push(at)
        cell.low.push(low)
        cell.high.push(high)
      } else {
        this.cells.set(key, { at: [at], low: [low], high: [high] })
      }
    }
  }

  /** How many spans on lines from *least* to *most* share more than SHARED of the stretch *low*–*high*. */
  sharing(low: number, high: number, least: number, most: number): number {
    let count = 0
    const lastAlong = Math.floor(high / CELL_ALONG)
    for (let across = Math.floor(least / CELL_ACROSS); across <= Math.floor(most / CELL_ACROSS); across += 1) {
      for (let along = Math.floor(low / CELL_ALONG); along <= lastAlong; along += 1) {
        const cell = this.cells.get(across * CELL_SPREAD + along)
        if (!cell) continue
        const { at, low: lows, high: highs } = cell
        for (let index = 0; index < at.length; index += 1) {
          if (at[index] < least || at[index] > most) continue
          const [spanLow, spanHigh] = [lows[index], highs[index]]
          const from = low > spanLow ? low : spanLow
          if (Math.floor(from / CELL_ALONG) !== along) continue
          if ((high < spanHigh ? high : spanHigh) - from > SHARED) count += 1
        }
      }
    }
    return count
  }
}

/** Spans along lines, level ones by their y and upright ones by their x. */
export class Lines {
  private readonly level = new Map<number, [number, number][]>()
  private readonly upright = new Map<number, [number, number][]>()
  private readonly levelAt: number[] = []
  private readonly uprightAt: number[] = []
  private readonly levelCells = new Cells()
  private readonly uprightCells = new Cells()

  add(a: Point, b: Point): void {
    if (a.y === b.y && a.x !== b.x) {
      if (!this.level.has(a.y)) {
        insertSorted(this.levelAt, a.y)
        this.level.set(a.y, [])
      }
      this.level.get(a.y)?.push([Math.min(a.x, b.x), Math.max(a.x, b.x)])
      this.levelCells.add(a.y, Math.min(a.x, b.x), Math.max(a.x, b.x))
    } else if (a.x === b.x && a.y !== b.y) {
      if (!this.upright.has(a.x)) {
        insertSorted(this.uprightAt, a.x)
        this.upright.set(a.x, [])
      }
      this.upright.get(a.x)?.push([Math.min(a.y, b.y), Math.max(a.y, b.y)])
      this.uprightCells.add(a.x, Math.min(a.y, b.y), Math.max(a.y, b.y))
    }
  }

  near(a: Point, b: Point, within: number): number {
    const at = a.y === b.y ? a.y : a.x
    return this.sharing(a, b, at - within + 1e-9, at + within - 1e-9)
  }

  between(a: Point, b: Point, least: number, most: number): number {
    return this.sharing(a, b, least, most)
  }

  /** How many spans on the lines from *least* to *most* share more than SHARED of the run a–b's stretch. */
  private sharing(a: Point, b: Point, least: number, most: number): number {
    const isLevel = a.y === b.y
    const low = isLevel ? Math.min(a.x, b.x) : Math.min(a.y, b.y)
    const high = isLevel ? Math.max(a.x, b.x) : Math.max(a.y, b.y)
    return (isLevel ? this.levelCells : this.uprightCells).sharing(low, high, least, most)
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
