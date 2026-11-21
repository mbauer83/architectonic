/**
 * Where a connector attaches, and the straight stub it leaves by.
 *
 * The TypeScript mirror of `src/domain/diagrams/layout/routing/ports.py`.
 */
import { fraction } from '../attachment'
import type { Extent, Point } from '../geometry'
import { heightOf, widthOf } from '../geometry'
import type { Port, Side } from '../orthogonal'
import { halfUp, leavesLevel } from '../orthogonal'
import { byText } from './scene'

export const OUTWARD_INDEX: Readonly<Record<Side, number>> = { right: 0, left: 1, bottom: 2, top: 3 }

export interface Stub {
  readonly port: Port
  readonly at: Point
  readonly end: Point
}

export const stubOf = (extent: Extent, side: Side, at: number, run: number): Stub => {
  const level = leavesLevel(side)
  const low = level ? extent.top : extent.left
  const high = level ? extent.bottom : extent.right
  const innerLow = Math.ceil(low)
  const innerHigh = Math.floor(high)
  const along =
    innerLow <= innerHigh ? Math.min(Math.max(halfUp(low + at * (high - low)), innerLow), innerHigh) : low
  const port: Port = { side, at: high > low ? fraction((along - low) / (high - low)) : 0.5 }
  const places: Record<Side, readonly [Point, Point]> = {
    top: [
      { x: along, y: extent.top },
      { x: along, y: Math.floor(extent.top - run) },
    ],
    bottom: [
      { x: along, y: extent.bottom },
      { x: along, y: Math.ceil(extent.bottom + run) },
    ],
    left: [
      { x: extent.left, y: along },
      { x: Math.floor(extent.left - run), y: along },
    ],
    right: [
      { x: extent.right, y: along },
      { x: Math.ceil(extent.right + run), y: along },
    ],
  }
  const [point, end] = places[side]
  return { port, at: point, end }
}

export interface EndOnSide {
  readonly connector: string
  readonly which: number
  readonly element: string
  readonly side: Side
  readonly toward: number
}

export const spread = (ends: readonly EndOnSide[]): Map<string, number> => {
  const sharing = new Map<string, EndOnSide[]>()
  for (const end of ends) {
    const key = `${end.element}\u0000${end.side}`
    const group = sharing.get(key)
    if (group) group.push(end)
    else sharing.set(key, [end])
  }
  const spreadAt = new Map<string, number>()
  for (const group of sharing.values()) {
    const ordered = [...group].sort(
      (one, other) => one.toward - other.toward || byText(one.connector, other.connector) || one.which - other.which,
    )
    ordered.forEach((end, position) =>
      spreadAt.set(`${end.connector}\u0000${end.which}`, (position + 1) / (ordered.length + 1)),
    )
  }
  return spreadAt
}

export const inLine = (source: Extent, target: Extent, sides: readonly [Side, Side]): [number, number] | null => {
  const level = leavesLevel(sides[0])
  if (sides[0] === sides[1] || leavesLevel(sides[1]) !== level) return null
  const low = level ? Math.max(source.top, target.top) : Math.max(source.left, target.left)
  const high = level ? Math.min(source.bottom, target.bottom) : Math.min(source.right, target.right)
  if (high - low < 2) return null
  const middle = halfUp((low + high) / 2)
  const share = (extent: Extent): number =>
    (middle - (level ? extent.top : extent.left)) / (level ? heightOf(extent) : widthOf(extent))
  return [share(source), share(target)]
}
