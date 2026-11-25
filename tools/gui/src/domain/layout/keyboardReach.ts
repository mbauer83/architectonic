/**
 * How the keyboard reaches what a diagram draws, in either mode (sketch 02·9, 05·5; Q8): the order the
 * shapes are walked in, and the nearest shape in an arrow's direction.
 */
import { centreOf, type Extent } from './geometry'

/** One shape as the keyboard reaches it: what names it, and where it is drawn. */
export interface Stop {
  readonly id: string
  readonly box: Extent
}

/** Shapes whose tops are within this of each other share a row. */
const ROW = 8

/** Top to bottom, then left to right; shapes whose tops are within a few units share a row. */
export const inReadingOrder = (one: Extent, other: Extent): number =>
  (Math.abs(one.top - other.top) > ROW ? one.top - other.top : one.left - other.left)

/** An arrow key as the direction it points in. */
export const ARROW_DIRECTIONS: Readonly<Record<string, { readonly x: number; readonly y: number }>> = {
  ArrowRight: { x: 1, y: 0 }, ArrowLeft: { x: -1, y: 0 }, ArrowDown: { x: 0, y: 1 }, ArrowUp: { x: 0, y: -1 },
}

/** The nearest of *stops* from *from* in *direction*: ahead of it, weighing sideways distance double. */
export const nearestTowards = <S extends Stop>(
  from: Extent, stops: readonly S[], direction: { readonly x: number; readonly y: number },
): S | null => {
  const here = centreOf(from)
  return stops.reduce<{ stop: S | null; score: number }>((best, stop) => {
    const there = centreOf(stop.box)
    const ahead = (there.x - here.x) * direction.x + (there.y - here.y) * direction.y
    const aside = Math.abs((there.x - here.x) * direction.y + (there.y - here.y) * direction.x)
    const score = ahead + 2 * aside
    return ahead > 0 && score < best.score ? { stop, score } : best
  }, { stop: null, score: Number.POSITIVE_INFINITY }).stop
}

/**
 * The shapes of a picture being edited in the order Tab walks them (02·9 second pass): elements in
 * reading order, each box just before its first member — outer boxes before inner ones — and a box
 * holding no element at its own place in the reading.
 */
export const walkOrder = (
  elements: readonly Stop[], boxes: readonly Stop[], containerOf: (id: string) => string | undefined,
): string[] => {
  const holding = new Set(elements.flatMap((element) => containersOf(element.id, containerOf)))
  const read = [...elements, ...boxes.filter((box) => !holding.has(box.id))]
    .sort((one, other) => inReadingOrder(one.box, other.box))
  const walked: string[] = []
  for (const stop of read) {
    const outerFirst = containersOf(stop.id, containerOf).reverse()
    walked.push(...[...outerFirst, stop.id].filter((id) => !walked.includes(id)))
  }
  return walked
}

/** The boxes *id* is drawn inside, nearest first. */
const containersOf = (id: string, containerOf: (id: string) => string | undefined): string[] => {
  const found: string[] = []
  for (let at = containerOf(id); at !== undefined && !found.includes(at); at = containerOf(at)) found.push(at)
  return found
}
