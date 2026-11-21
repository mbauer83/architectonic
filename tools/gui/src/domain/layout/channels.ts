/**
 * The gaps between boxes that lines run along, and whether each is wide enough for the lines in it.
 *
 * The TypeScript mirror of `src/domain/diagrams/layout/channels.py`. A channel is the clear gap
 * between two boxes side by side in one parent, or between a box and the border of the box it sits
 * in; the lines laid along it must fit at the spacing nudging places them at, IDEAL_SEPARATION from
 * each border and from each other.
 */
import type { Extent, Point } from './geometry'
import { encloses } from './geometry'
import { IDEAL_SEPARATION, byText, sameExtent } from './routing/scene'

const SHARED = 1

export type Across = 'x' | 'y'

export interface Channel {
  /** The two boxes, the one with the lower coordinate first. */
  readonly low: string
  readonly high: string
  /** Which coordinate the gap spans: 'x' for boxes side by side, 'y' for one above the other. */
  readonly across: Across
  /** Where the gap starts and ends, across it. */
  readonly start: number
  readonly end: number
  /** Where it starts and ends, along it. */
  readonly first: number
  readonly last: number
  /** How many lines run along it. */
  readonly lines: number
}

const channelOf = (
  low: string,
  high: string,
  across: Across,
  start: number,
  end: number,
  first: number,
  last: number,
): Channel => ({ low, high, across, start, end, first, last, lines: 0 })

export const widthOf = (channel: Channel): number => channel.end - channel.start

/** How much wider the channel needs to be for its lines, in whole pixels; 0 where they fit. */
export const widerBy = (channel: Channel): number => {
  if (channel.lines === 0) return 0
  const needed = (channel.lines + 1) * IDEAL_SEPARATION
  return Math.max(0, Math.ceil(needed - widthOf(channel)))
}

/** Each box's parent: the smallest other box that encloses it, or null at the top. */
export const parentsOf = (boxes: ReadonlyMap<string, Extent>): Map<string, string | null> => {
  const parents = new Map<string, string | null>()
  for (const [key, box] of boxes) {
    let best: [number, string] | null = null
    for (const [otherKey, other] of boxes) {
      if (otherKey === key || !encloses(other, box) || sameExtent(other, box)) continue
      const area = (other.right - other.left) * (other.bottom - other.top)
      const smaller = best === null || area < best[0] || (area === best[0] && byText(otherKey, best[1]) < 0)
      if (smaller) best = [area, otherKey]
    }
    parents.set(key, best === null ? null : best[1])
  }
  return parents
}

const regionOf = (channel: Channel): Extent =>
  channel.across === 'x'
    ? { left: channel.start, top: channel.first, right: channel.end, bottom: channel.last }
    : { left: channel.first, top: channel.start, right: channel.last, bottom: channel.end }

const between = (low: string, high: string, lower: Extent, upper: Extent, across: Across): Channel | null => {
  const [start, end, first, last] =
    across === 'x'
      ? [lower.right, upper.left, Math.max(lower.top, upper.top), Math.min(lower.bottom, upper.bottom)]
      : [lower.bottom, upper.top, Math.max(lower.left, upper.left), Math.min(lower.right, upper.right)]
  return end > start && last - first > SHARED ? channelOf(low, high, across, start, end, first, last) : null
}

const inside = (child: string, parent: string, inner: Extent, outer: Extent): Channel[] =>
  [
    channelOf(parent, child, 'x', outer.left, inner.left, inner.top, inner.bottom),
    channelOf(child, parent, 'x', inner.right, outer.right, inner.top, inner.bottom),
    channelOf(parent, child, 'y', outer.top, inner.top, inner.left, inner.right),
    channelOf(child, parent, 'y', inner.bottom, outer.bottom, inner.left, inner.right),
  ].filter((channel) => widthOf(channel) > 0 && channel.last - channel.first > SHARED)

const clear = (
  region: Extent,
  keys: readonly [string, string],
  boxes: ReadonlyMap<string, Extent>,
  others: readonly Extent[],
): boolean => {
  const standing = [
    ...[...boxes].filter(([key, box]) => !keys.includes(key) && !encloses(box, region)).map(([, box]) => box),
    ...others,
  ]
  return !standing.some((shape) => {
    const width = Math.min(region.right, shape.right) - Math.max(region.left, shape.left)
    const height = Math.min(region.bottom, shape.bottom) - Math.max(region.top, shape.top)
    return width > SHARED && height > SHARED
  })
}

const runsAlong = (channel: Channel, course: readonly Point[]): boolean => {
  for (let index = 1; index < course.length; index += 1) {
    const a = course[index - 1]
    const b = course[index]
    const upright = a.x === b.x && a.y !== b.y
    const level = a.y === b.y && a.x !== b.x
    let low: number
    let high: number
    if (channel.across === 'x' && upright && channel.start < a.x && a.x < channel.end) {
      low = Math.min(a.y, b.y)
      high = Math.max(a.y, b.y)
    } else if (channel.across === 'y' && level && channel.start < a.y && a.y < channel.end) {
      low = Math.min(a.x, b.x)
      high = Math.max(a.x, b.x)
    } else continue
    if (Math.min(high, channel.last) - Math.max(low, channel.first) > SHARED) return true
  }
  return false
}

/** Every clear channel between *boxes*, with how many of *courses* run along each. */
export const channels = (
  boxes: ReadonlyMap<string, Extent>,
  others: readonly Extent[],
  courses: readonly (readonly Point[])[],
): Channel[] => {
  const parents = parentsOf(boxes)
  const keys = [...boxes.keys()].sort(byText)
  const box = (key: string): Extent => boxes.get(key) as Extent
  const found: Channel[] = []
  keys.forEach((one, index) => {
    const parent = parents.get(one) ?? null
    if (parent !== null) found.push(...inside(one, parent, box(one), box(parent)))
    for (const other of keys.slice(index + 1)) {
      if ((parents.get(other) ?? null) !== parent) continue
      for (const across of ['x', 'y'] as const) {
        for (const [low, high] of [
          [one, other],
          [other, one],
        ] as const) {
          const channel = between(low, high, box(low), box(high), across)
          if (channel) found.push(channel)
        }
      }
    }
  })
  return found
    .filter((channel) => clear(regionOf(channel), [channel.low, channel.high], boxes, others))
    .map((channel) => ({ ...channel, lines: courses.filter((course) => runsAlong(channel, course)).length }))
}

/** The channels too narrow for the lines that run along them. */
export const tooNarrow = (
  boxes: ReadonlyMap<string, Extent>,
  others: readonly Extent[],
  courses: readonly (readonly Point[])[],
): Channel[] => channels(boxes, others, courses).filter((channel) => widerBy(channel) > 0)
