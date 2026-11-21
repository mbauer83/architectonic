/**
 * Nudging (GD 2009 §5): runs that share a line are pulled apart, and none stays along a box border.
 *
 * The TypeScript mirror of `src/domain/diagrams/layout/routing/nudging.py`.
 */
import type { Extent, Point } from '../geometry'
import { halfUp } from '../orthogonal'
import { LINE_CLEARANCE } from '../routeQuality'
import { IDEAL_SEPARATION, byText } from './scene'

const SHARED = 1
const PASSES = 50
const UNBOUNDED = 1.0e9
const FAR = 500
const ROUNDS = 4
const SWEEPS = 2

const pairsOf = (cluster: readonly Member[]): [string, string][] => {
  const ordered = [...cluster].sort((one, other) => one.at - other.at || byText(one.owner, other.owner) || one.index - other.index)
  return ordered.slice(1).flatMap((second, index): [string, string][] => {
    const first = ordered[index]
    if (!(second.at - first.at < LINE_CLEARANCE + 1) || !(first.owner || second.owner) || first.owner === second.owner) return []
    const one = first.owner || second.owner
    const other = second.owner || first.owner
    return [[byText(one, other) <= 0 ? one : other, byText(one, other) <= 0 ? other : one]]
  })
}

const apart = (cluster: readonly Member[]): boolean => {
  const ats = cluster.map((member) => member.at).sort((one, other) => one - other)
  return ats.every((at, index) => index === 0 || at - ats[index - 1] >= LINE_CLEARANCE + 1)
}

interface Member {
  readonly at: number
  readonly low: number
  readonly high: number
  readonly least: number
  readonly most: number
  readonly turns: number
  readonly owner: string
  readonly index: number
}

const movableOf = (member: Member): boolean => member.least < member.most

const across = (point: Point, level: boolean): number => (level ? point.y : point.x)
const along = (point: Point, level: boolean): number => (level ? point.x : point.y)

const freeSpace = (
  course: readonly Point[],
  index: number,
  level: boolean,
  obstacles: readonly Extent[],
  outward: readonly number[],
): [number, number] => {
  const a = course[index]
  const b = course[index + 1]
  const at = across(a, level)
  const low = Math.min(along(a, level), along(b, level))
  const high = Math.max(along(a, level), along(b, level))
  let least = -UNBOUNDED
  let most = UNBOUNDED
  for (const neighbour of [course[index - 1], course[index + 2]]) {
    const far = across(neighbour, level)
    if (far < at) least = Math.max(least, far + 1)
    else most = Math.min(most, far - 1)
  }
  for (const rect of obstacles) {
    const rLow = level ? rect.left : rect.top
    const rHigh = level ? rect.right : rect.bottom
    const rNear = level ? rect.top : rect.left
    const rFar = level ? rect.bottom : rect.right
    if (Math.max(rLow, low) < Math.min(rHigh, high)) {
      if (rFar <= at) least = Math.max(least, rFar)
      else if (rNear >= at) most = Math.min(most, rNear)
    }
  }
  for (const sign of outward) {
    if (sign < 0) most = Math.min(most, at)
    else least = Math.max(least, at)
  }
  return [least, most]
}

const turnsOf = (course: readonly Point[], index: number, level: boolean): number => {
  const at = across(course[index], level)
  let total = 0
  for (const neighbour of [course[index - 1], course[index + 2]]) {
    const far = across(neighbour, level)
    total += far < at ? -1 : far > at ? 1 : 0
  }
  return total
}

const membersOf = (
  courses: ReadonlyMap<string, Point[]>,
  level: boolean,
  movable: ReadonlySet<string> | null,
  obstacles: ReadonlyMap<string, readonly Extent[]>,
  fixed: readonly (readonly [number, number, number])[],
): Member[] => {
  const members: Member[] = fixed.map(([at, low, high]) => ({
    at,
    low,
    high,
    least: at,
    most: at,
    turns: 0,
    owner: '',
    index: -1,
  }))
  for (const key of [...courses.keys()].sort(byText)) {
    const course = courses.get(key) ?? []
    const last = course.length - 2
    for (let index = 0; index <= last; index += 1) {
      const a = course[index]
      const b = course[index + 1]
      const runsLevel = a.y === b.y && a.x !== b.x
      if (runsLevel !== level || (!level && a.x !== b.x)) continue
      const at = across(a, level)
      const low = Math.min(along(a, level), along(b, level))
      const high = Math.max(along(a, level), along(b, level))
      if (index === 0 || index === last || (movable !== null && !movable.has(key))) {
        members.push({ at, low, high, least: at, most: at, turns: 0, owner: key, index })
        continue
      }
      const outward: number[] = []
      if (index === 1) outward.push(across(course[1], level) > across(course[0], level) ? 1 : -1)
      if (index === last - 1) outward.push(across(course[last], level) > across(course[last + 1], level) ? 1 : -1)
      const [least, most] = freeSpace(course, index, level, obstacles.get(key) ?? [], outward)
      members.push({ at, low, high, least, most, turns: turnsOf(course, index, level), owner: key, index })
    }
  }
  return members
}

const clustersOf = (members: readonly Member[]): Member[][] => {
  const parent = members.map((_, index) => index)
  const root = (start: number): number => {
    let index = start
    while (parent[index] !== index) {
      parent[index] = parent[parent[index]]
      index = parent[index]
    }
    return index
  }
  const order = members.map((_, index) => index).sort((one, other) => members[one].at - members[other].at || one - other)
  order.forEach((first, position) => {
    for (const second of order.slice(position + 1)) {
      if (members[second].at - members[first].at >= IDEAL_SEPARATION) break
      const one = members[first]
      const other = members[second]
      if (Math.min(one.high, other.high) - Math.max(one.low, other.low) > SHARED) parent[root(second)] = root(first)
    }
  })
  const groups = new Map<number, Member[]>()
  for (const index of order) {
    const key = root(index)
    const group = groups.get(key)
    if (group) group.push(members[index])
    else groups.set(key, [members[index]])
  }
  return [...groups.values()].filter((group) => group.length > 1)
}

const placed = (ordered: readonly Member[], separation: number): number[] | null => {
  const movable = ordered.filter(movableOf)
  let total = 0
  for (const member of movable) total += member.at
  const centre = total / movable.length
  const rank = new Map(movable.map((member, position) => [member, position]))
  const places = ordered.map((member) =>
    movableOf(member) ? centre + ((rank.get(member) ?? 0) - (movable.length - 1) / 2) * separation : member.at,
  )
  for (let pass = 0; pass < PASSES; pass += 1) {
    ordered.forEach((member, index) => {
      places[index] = Math.min(Math.max(places[index], member.least), member.most)
    })
    for (let index = 1; index < ordered.length; index += 1) {
      if (places[index] < places[index - 1] + separation) {
        if (movableOf(ordered[index])) places[index] = places[index - 1] + separation
        else if (movableOf(ordered[index - 1])) places[index - 1] = places[index] - separation
      }
    }
    for (let index = ordered.length - 2; index >= 0; index -= 1) {
      if (places[index] > places[index + 1] - separation) {
        if (movableOf(ordered[index])) places[index] = places[index + 1] - separation
        else if (movableOf(ordered[index + 1])) places[index + 1] = places[index] + separation
      }
    }
    const fits =
      ordered.every((member, index) => member.least <= places[index] && places[index] <= member.most) &&
      places.every((place, index) => index === 0 || place - places[index - 1] >= separation - 1e-9)
    if (fits) return places
  }
  return null
}

const middleOf = (member: Member): number =>
  (Math.max(member.least, member.at - FAR) + Math.min(member.most, member.at + FAR)) / 2

const firstThatFits = (cluster: readonly Member[]): [Member[], number[] | null] => {
  const orders = [
    [...cluster].sort(
      (one, other) =>
        one.turns - other.turns || middleOf(one) - middleOf(other) || byText(one.owner, other.owner) || one.index - other.index,
    ),
    [...cluster].sort(
      (one, other) => middleOf(one) - middleOf(other) || byText(one.owner, other.owner) || one.index - other.index,
    ),
  ]
  for (const separation of [IDEAL_SEPARATION, LINE_CLEARANCE + 1]) {
    for (const ordered of orders) {
      const places = placed(ordered, separation)
      if (places) return [ordered, places]
    }
  }
  return [orders[0], null]
}

const fixedLinesOf = (
  borders: readonly Extent[],
  fixedLines: readonly (readonly Point[])[],
  level: boolean,
): (readonly [number, number, number])[] => [
  ...borders.flatMap((box): (readonly [number, number, number])[] =>
    level
      ? [
          [box.top, box.left, box.right],
          [box.bottom, box.left, box.right],
        ]
      : [
          [box.left, box.top, box.bottom],
          [box.right, box.top, box.bottom],
        ],
  ),
  ...fixedLines.flatMap((line) =>
    line.slice(1).flatMap((b, index): (readonly [number, number, number])[] => {
      const a = line[index]
      const sameLine = level ? a.y === b.y : a.x === b.x
      if (!sameLine || (a.x === b.x && a.y === b.y)) return []
      return [[across(a, level), Math.min(along(a, level), along(b, level)), Math.max(along(a, level), along(b, level))]]
    }),
  ),
]

const separated = (
  moved: Map<string, Point[]>,
  level: boolean,
  movable: ReadonlySet<string> | null,
  obstacles: ReadonlyMap<string, readonly Extent[]>,
  fixed: readonly (readonly [number, number, number])[],
): void => {
  for (let round = 0; round < ROUNDS; round += 1) {
    let changed = false
    for (const cluster of clustersOf(membersOf(moved, level, movable, obstacles, fixed))) {
      if (apart(cluster) || !cluster.some(movableOf)) continue
      const [ordered, places] = firstThatFits(cluster)
      if (!places) continue
      ordered.forEach((member, index) => {
        const whole = halfUp(places[index])
        if (movableOf(member) && member.at !== whole) {
          changed = true
          const course = moved.get(member.owner)
          if (!course) return
          for (const at of [member.index, member.index + 1]) {
            course[at] = level ? { x: course[at].x, y: whole } : { x: whole, y: course[at].y }
          }
        }
      })
    }
    if (!changed) return
  }
}

export const nudged = (
  courses: ReadonlyMap<string, readonly Point[]>,
  obstacles: ReadonlyMap<string, readonly Extent[]>,
  borders: readonly Extent[],
  fixedLines: readonly (readonly Point[])[] = [],
  movable: ReadonlySet<string> | null = null,
): [Map<string, Point[]>, [string, string][]] => {
  const moved = new Map([...courses].map(([key, course]) => [key, [...course]]))
  for (let sweep = 0; sweep < SWEEPS; sweep += 1) {
    for (const level of [true, false]) separated(moved, level, movable, obstacles, fixedLinesOf(borders, fixedLines, level))
  }
  const unseparated = [true, false].flatMap((level) =>
    clustersOf(membersOf(moved, level, movable, obstacles, fixedLinesOf(borders, fixedLines, level)))
      .filter((cluster) => !apart(cluster))
      .flatMap(pairsOf),
  )
  return [moved, unseparated]
}
