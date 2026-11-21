/**
 * Where nudging places the runs of one cluster: an order, then places each two sharing a stretch apart.
 *
 * The TypeScript mirror of `src/domain/diagrams/layout/routing/placement.py`.
 */
import { LINE_CLEARANCE } from '../routeQuality'
import { IDEAL_SEPARATION, byText } from './scene'

const SHARED = 1
const PASSES = 50
const FAR = 500
/** The most members a cluster may have for every order of it to be tried. */
const PERMUTED = 6

export interface Member {
  readonly at: number
  readonly low: number
  readonly high: number
  least: number
  most: number
  readonly turns: number
  readonly owner: string
  readonly index: number
}

export const share = (one: Member, other: Member): boolean =>
  Math.min(one.high, other.high) - Math.max(one.low, other.low) > SHARED

export const movableOf = (member: Member): boolean => member.least < member.most

/** Places for *ordered*, in its order, each two that share a stretch *separation* apart; or null. */
const placed = (ordered: readonly Member[], separation: number): number[] | null => {
  const places = ordered.map((member) => member.at)
  const before = ordered.map((later, position) =>
    ordered
      .slice(0, position)
      .map((earlier, index) => (share(earlier, later) ? index : -1))
      .filter((index) => index >= 0),
  )
  for (let pass = 0; pass < PASSES; pass += 1) {
    ordered.forEach((member, index) => {
      places[index] = Math.min(Math.max(places[index], member.least), member.most)
    })
    for (let later = 0; later < ordered.length; later += 1) {
      for (const earlier of before[later]) {
        if (places[later] < places[earlier] + separation) {
          if (movableOf(ordered[later])) places[later] = places[earlier] + separation
          else if (movableOf(ordered[earlier])) places[earlier] = places[later] - separation
        }
      }
    }
    for (let later = ordered.length - 1; later >= 0; later -= 1) {
      for (const earlier of [...before[later]].reverse()) {
        if (places[earlier] > places[later] - separation) {
          if (movableOf(ordered[earlier])) places[earlier] = places[later] - separation
          else if (movableOf(ordered[later])) places[later] = places[earlier] + separation
        }
      }
    }
    const fits =
      ordered.every((member, index) => member.least <= places[index] && places[index] <= member.most) &&
      before.every((earliers, later) =>
        earliers.every((earlier) => places[later] - places[earlier] >= separation - 1e-9),
      )
    if (fits) return places
  }
  return null
}

/** Every order of *items*, in the order Python's itertools.permutations gives them. */
function* permutationsOf<T>(items: readonly T[]): Generator<T[]> {
  if (items.length <= 1) {
    yield [...items]
    return
  }
  for (let index = 0; index < items.length; index += 1) {
    const rest = [...items.slice(0, index), ...items.slice(index + 1)]
    for (const tail of permutationsOf(rest)) yield [items[index], ...tail]
  }
}

/** Places for a cluster no order fits as a whole: each run in turn nearest where it lies, clear of those before. */
const oneByOne = (ordered: readonly Member[]): number[] => {
  const places = new Map(ordered.map((member) => [member, member.at]))
  const done = ordered.filter((member) => !movableOf(member))
  const placeOf = (member: Member): number => places.get(member) ?? member.at
  for (const member of ordered) {
    if (!movableOf(member)) continue
    const sharing = done.filter((other) => share(member, other))
    for (const separation of [IDEAL_SEPARATION, LINE_CLEARANCE + 1]) {
      const beside = sharing.flatMap((other) => [-1, 1].map((sign) => placeOf(other) + sign * separation))
      const candidates = [member.at, ...beside]
      const clear = candidates.filter(
        (place) =>
          member.least <= place &&
          place <= member.most &&
          sharing.every((other) => Math.abs(place - placeOf(other)) >= separation - 1e-9),
      )
      if (clear.length > 0) {
        const nearest = clear.reduce((best, place) => {
          const [distance, bestDistance] = [Math.abs(place - member.at), Math.abs(best - member.at)]
          return distance < bestDistance || (distance === bestDistance && place < best) ? place : best
        })
        places.set(member, nearest)
        break
      }
    }
    done.push(member)
  }
  return ordered.map(placeOf)
}

const middleOf = (member: Member): number =>
  (Math.max(member.least, member.at - FAR) + Math.min(member.most, member.at + FAR)) / 2

const lowerBound = (sorted: readonly number[], value: number): number => {
  let low = 0
  let high = sorted.length
  while (low < high) {
    const middle = (low + high) >> 1
    if (sorted[middle] < value) low = middle + 1
    else high = middle
  }
  return low
}

export const firstThatFits = (cluster: readonly Member[]): [Member[], number[] | null] => {
  const fixed = cluster
    .filter((member) => !movableOf(member))
    .map((member) => member.at)
    .sort((one, other) => one - other)
  const band = (member: Member): number => lowerBound(fixed, member.at)
  const orders = [
    [...cluster].sort(
      (one, other) =>
        band(one) - band(other) ||
        one.turns - other.turns ||
        middleOf(one) - middleOf(other) ||
        byText(one.owner, other.owner) ||
        one.index - other.index,
    ),
    [...cluster].sort(
      (one, other) =>
        band(one) - band(other) ||
        middleOf(one) - middleOf(other) ||
        byText(one.owner, other.owner) ||
        one.index - other.index,
    ),
    [...cluster].sort((one, other) => one.at - other.at || byText(one.owner, other.owner) || one.index - other.index),
  ]
  const every = cluster.length <= PERMUTED ? [...orders, ...permutationsOf(orders[0])] : orders
  for (const separation of [IDEAL_SEPARATION, LINE_CLEARANCE + 1]) {
    for (const ordered of every) {
      const places = placed(ordered, separation)
      if (places) return [ordered, places]
    }
  }
  return [orders[0], oneByOne(orders[0])]
}
