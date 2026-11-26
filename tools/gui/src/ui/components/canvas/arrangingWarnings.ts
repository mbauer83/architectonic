/**
 * What the canvas marks while a picture is arranged, never refusing it (D6, Q12):
 *
 * - **hidden** — an element a shape painted after it covers: a box that does not hold it, or another
 *   element. A temporary position, which the verifier warns about; the mark says what lies beneath.
 * - **overlapping** — two connected elements over each other, which no route can satisfy. Marked, and
 *   Save stays available: the verifier reports it.
 */
import type { Extent } from '../../../domain/layout/geometry'
import { overlaps } from '../../../domain/layout/geometry'
import type { Breach } from '../../../domain/layout/canvasBreaches'
import type { Placement } from '../../../domain/layout/canvasRouting'

/** An element covered, and the first shape painted after it that covers it: what it is hidden behind. */
export interface Hidden {
  readonly alias: string
  readonly by: string
}

/** Each element covered by a shape painted after it that does not hold it, by alias. */
export const hiddenElements = (
  order: readonly string[], placement: Placement, insideOf: ReadonlyMap<string, string | undefined>,
): readonly Hidden[] => {
  const holders = (alias: string): ReadonlySet<string> => {
    const chain = new Set<string>()
    for (let at = insideOf.get(alias); at !== undefined && !chain.has(at); at = insideOf.get(at)) chain.add(at)
    return chain
  }
  const extentOf = (alias: string): Extent | undefined => placement.elements.get(alias) ?? placement.boxes.get(alias)
  return order.flatMap((alias, index) => {
    const extent = placement.elements.get(alias)
    if (!extent) return []
    const held = holders(alias)
    const by = order.slice(index + 1).find((later) => {
      const over = extentOf(later)
      return !held.has(later) && !holders(later).has(alias) && over !== undefined && overlaps(over, extent)
    })
    return by === undefined ? [] : [{ alias, by }]
  })
}

/** The relations whose two ends are over each other, each once, by its place on the picture. */
export const overlappingEnds = (breaches: readonly Breach[]): ReadonlySet<number> =>
  new Set(breaches.filter((breach) => breach.rule === 'ends-overlap').map((breach) => breach.relation))
