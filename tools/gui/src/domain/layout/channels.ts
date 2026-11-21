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
  /** The longest straight run out of a shape facing it, of a line ending there; 0 for none. */
  readonly run: number
}

const channelOf = (
  low: string,
  high: string,
  across: Across,
  start: number,
  end: number,
  first: number,
  last: number,
): Channel => ({ low, high, across, start, end, first, last, lines: 0, run: 0 })

/** How far a gap may fall short and still fit: the rounding of a layout to whole pixels. */
const ROUNDING = 1

export const widthOf = (channel: Channel): number => channel.end - channel.start

/** How much wider the channel needs to be for its lines, in whole pixels; 0 where they fit. */
export const widerBy = (channel: Channel): number => {
  const along = channel.lines ? (channel.lines + 1) * IDEAL_SEPARATION : 0
  const outOf = channel.run ? channel.run + IDEAL_SEPARATION : 0
  return Math.max(0, Math.ceil(Math.max(along, outOf) - widthOf(channel) - ROUNDING))
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

/** The longest run of a line ending on a shape that faces *channel* (not one enclosing the gap). */
const runOutOf = (
  channel: Channel,
  shapes: ReadonlyMap<string, Extent>,
  ends: readonly (readonly [Point, number])[],
): number => {
  const region = regionOf(channel)
  const edges = [
    [channel.low, channel.start],
    [channel.high, channel.end],
  ]
    .filter(([key]) => !encloses(shapes.get(key as string) as Extent, region))
    .map(([, edge]) => edge as number)
  let longest = 0
  for (const [point, run] of ends) {
    const across = channel.across === 'x' ? point.x : point.y
    const along = channel.across === 'x' ? point.y : point.x
    if (edges.some((edge) => Math.abs(across - edge) <= SHARED) && channel.first <= along && along <= channel.last) {
      longest = Math.max(longest, run)
    }
  }
  return longest
}

/** The channels between each element and the border of the smallest box holding it. */
const memberChannels = (boxes: ReadonlyMap<string, Extent>, members: ReadonlyMap<string, Extent>): Channel[] =>
  [...members.keys()].sort(byText).flatMap((key) => {
    const member = members.get(key) as Extent
    let best: [number, string] | null = null
    for (const [boxKey, box] of boxes) {
      if (!encloses(box, member) || sameExtent(box, member)) continue
      const area = (box.right - box.left) * (box.bottom - box.top)
      if (best === null || area < best[0] || (area === best[0] && byText(boxKey, best[1]) < 0)) best = [area, boxKey]
    }
    return best ? inside(key, best[1], member, boxes.get(best[1]) as Extent) : []
  })

/**
 * Every clear channel between *boxes*, and between *members* and their boxes, with how many of
 * *courses* run along each and the longest of *ends* — a line's end and its straight run — out of it.
 */
export const channels = (
  boxes: ReadonlyMap<string, Extent>,
  others: readonly Extent[],
  courses: readonly (readonly Point[])[],
  members: ReadonlyMap<string, Extent> = new Map(),
  ends: readonly (readonly [Point, number])[] = [],
): Channel[] => {
  const parents = parentsOf(boxes)
  const keys = [...boxes.keys()].sort(byText)
  const box = (key: string): Extent => boxes.get(key) as Extent
  const found: Channel[] = memberChannels(boxes, members)
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
  const shapes = new Map([...members, ...boxes])
  return found
    .filter((channel) => {
      const own = [shapes.get(channel.low) as Extent, shapes.get(channel.high) as Extent]
      const standing = others.filter((other) => !own.some((shape) => sameExtent(shape, other)))
      return clear(regionOf(channel), [channel.low, channel.high], boxes, standing)
    })
    .map((channel) => ({
      ...channel,
      lines: courses.filter((course) => runsAlong(channel, course)).length,
      run: runOutOf(channel, shapes, ends),
    }))
}

/** The channels too narrow for the lines that run along them, or the runs out of them. */
export const tooNarrow = (
  boxes: ReadonlyMap<string, Extent>,
  others: readonly Extent[],
  courses: readonly (readonly Point[])[],
  members: ReadonlyMap<string, Extent> = new Map(),
  ends: readonly (readonly [Point, number])[] = [],
): Channel[] => channels(boxes, others, courses, members, ends).filter((channel) => widerBy(channel) > 0)
