/**
 * Nudging (GD 2009 §5): runs that share a line are pulled apart, and none stays along a box border.
 *
 * The TypeScript mirror of `src/domain/diagrams/layout/routing/nudging.py`.
 */
import type { Extent, Point } from '../geometry'
import { halfUp } from '../orthogonal'
import { END_RUN, LINE_CLEARANCE } from '../routeQuality'
import type { Member } from './placement'
import { firstThatFits, movableOf, preferredPlaces, share } from './placement'
import { IDEAL_SEPARATION, byText } from './scene'

const UNBOUNDED = 1.0e9
const ROUNDS = 4
const SWEEPS = 2
/** How near two members sharing a stretch must lie to be placed together: twice the ideal separation. */
const REACH = 2 * IDEAL_SEPARATION

/** The connectors whose runs share a stretch closer than the least separation. */
const pairsOf = (cluster: readonly Member[]): [string, string][] => {
  const ordered = [...cluster].sort(
    (one, other) => one.at - other.at || byText(one.owner, other.owner) || one.index - other.index,
  )
  return ordered.flatMap((first, position) =>
    ordered.slice(position + 1).flatMap((second): [string, string][] => {
      if (!(second.at - first.at < LINE_CLEARANCE + 1) || !share(first, second)) return []
      if (!(first.owner || second.owner) || first.owner === second.owner) return []
      const one = first.owner || second.owner
      const other = second.owner || first.owner
      return [[byText(one, other) <= 0 ? one : other, byText(one, other) <= 0 ? other : one]]
    }),
  )
}

/** Whether each two members of a cluster that share a stretch lie at least the least separation apart. */
const apart = (cluster: readonly Member[]): boolean =>
  cluster.every((first, position) =>
    cluster
      .slice(position + 1)
      .every((second) => !share(first, second) || Math.abs(second.at - first.at) >= LINE_CLEARANCE + 1),
  )

const across = (point: Point, level: boolean): number => (level ? point.y : point.x)
const along = (point: Point, level: boolean): number => (level ? point.x : point.y)

const freeSpace = (
  course: readonly Point[],
  index: number,
  level: boolean,
  obstacles: readonly Extent[],
  outward: readonly (readonly [number, number])[],
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
  for (const [sign, nearest] of outward) {
    if (sign < 0) most = Math.min(most, nearest)
    else least = Math.max(least, nearest)
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
      // The run next to an end keeps the end's run at least END_RUN long, or as long as it is.
      const outward: [number, number][] = []
      const ends: readonly (readonly [boolean, Point, Point])[] = [
        [index === 1, course[0], course[1]],
        [index === last - 1, course[last + 1], course[last]],
      ]
      for (const [nextToEnd, port, beside] of ends) {
        if (!nextToEnd) continue
        const sign = across(beside, level) > across(port, level) ? 1 : -1
        const reach = across(port, level) + sign * END_RUN
        outward.push([sign, sign > 0 ? Math.min(at, reach) : Math.max(at, reach)])
      }
      const [least, most] = freeSpace(course, index, level, obstacles.get(key) ?? [], outward)
      members.push({ at, low, high, least, most, turns: turnsOf(course, index, level), owner: key, index })
    }
  }
  return clearOfTheFixed(members)
}

/** Each run's free space kept the least separation clear of every box border and line drawn already. */
const clearOfTheFixed = (members: Member[]): Member[] => {
  const fixed = members.filter((member) => !member.owner)
  for (const member of members) {
    if (!movableOf(member)) continue
    for (const line of fixed) {
      if (!share(member, line)) continue
      if (line.at > member.at) member.most = Math.min(member.most, line.at - (LINE_CLEARANCE + 1))
      else if (line.at < member.at) member.least = Math.max(member.least, line.at + (LINE_CLEARANCE + 1))
    }
    if (member.least > member.most) {
      member.least = member.at
      member.most = member.at
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
  const order = members
    .map((_, index) => index)
    .sort((one, other) => members[one].at - members[other].at || one - other)
  order.forEach((first, position) => {
    for (const second of order.slice(position + 1)) {
      if (members[second].at - members[first].at >= REACH) break
      const one = members[first]
      const other = members[second]
      if (share(one, other)) parent[root(second)] = root(first)
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
      const [from, to] = [along(a, level), along(b, level)]
      return [[across(a, level), Math.min(from, to), Math.max(from, to)]]
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
      if (!cluster.some(movableOf)) continue
      const [ordered, places] = apart(cluster) ? [cluster, preferredPlaces(cluster)] : firstThatFits(cluster)
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
    for (const level of [true, false]) {
      separated(moved, level, movable, obstacles, fixedLinesOf(borders, fixedLines, level))
    }
  }
  const unseparated = [true, false].flatMap((level) =>
    clustersOf(membersOf(moved, level, movable, obstacles, fixedLinesOf(borders, fixedLines, level)))
      .filter((cluster) => !apart(cluster))
      .flatMap(pairsOf),
  )
  return [moved, unseparated]
}
