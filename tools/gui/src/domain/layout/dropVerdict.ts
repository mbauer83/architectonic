/**
 * What becomes of an element dropped on another shape (sketch 03·9–10, D7, Q13), said in words:
 *
 * - **into** a box that takes it — one of the diagram's own groupings whose rule admits it: diagram
 *   content, no question ("Into Business");
 * - **nest** in an element that may hold it by a relationship of the containment kind: a question
 *   follows ("Nest in Submit Proposed Changes for Review…", the ellipsis announcing it);
 * - **refused** by a box whose rule does not admit it, or an element the ontology permits no part-of
 *   relationship to: nothing lights up while it is dragged, and on release one line says why;
 * - nothing to say: dropped where it already is, or on a box that draws it by its rule anyway, or while
 *   the ontology's answer is still awaited.
 */
import type { Admission } from './receivingBox'
import { admitsType } from './receivingBox'

export type DropVerdict =
  | { readonly kind: 'into' | 'nest'; readonly words: string }
  | { readonly kind: 'refused'; readonly why: string }

/** The element dropped: its name, type and the layer its type belongs to. */
export interface Dropped {
  readonly name: string
  readonly type: string
  readonly domain: string | undefined
}

/** The shape it was dropped on. */
export type DropTarget =
  /** One of the diagram's own groupings, or a box its rule draws (*ruled*), and what it admits. */
  | { readonly kind: 'box'; readonly name: string; readonly ruled: boolean; readonly admits: Admission }
  /** An element, and the containment relationships the ontology permits from it to the one dropped;
   * undefined until known. */
  | { readonly kind: 'element'; readonly name: string; readonly type: string; readonly holds?: readonly string[] }

/** How a type is said in a sentence: its words, as the menus print them. */
export type TypeWords = (type: string) => string

/** A noun with its indefinite article: "an application function", "a business object". */
const indefinite = (noun: string): string => `${/^[aeiou]/i.test(noun) ? 'an' : 'a'} ${noun}`

const what = (admits: Admission, words: TypeWords): string => {
  switch (admits.kind) {
    case 'domain': return `${admits.domain} elements`
    case 'type': return `${words(admits.type)} elements`
    case 'anything': case 'parts': return 'its own parts'
  }
}

const boxVerdict = (
  dropped: Dropped, box: Extract<DropTarget, { kind: 'box' }>, words: TypeWords,
): DropVerdict | null => {
  if (admitsType(box.admits, dropped.type, dropped.domain ?? '')) {
    return box.ruled ? null : { kind: 'into', words: `Into ${box.name}` }
  }
  return {
    kind: 'refused',
    why: `${box.name} holds ${what(box.admits, words)} only; ${dropped.name} is ${indefinite(words(dropped.type))}`
      + `${dropped.domain ? ` (${dropped.domain})` : ''}.`,
  }
}

/** What dropping *dropped* on *target* does, in words; null where there is nothing to say. */
export const dropVerdict = (dropped: Dropped, target: DropTarget, words: TypeWords): DropVerdict | null => {
  if (target.kind === 'box') return boxVerdict(dropped, target, words)
  if (target.holds === undefined) return null
  return target.holds.length > 0 ? { kind: 'nest', words: `Nest in ${target.name}…` } : {
    kind: 'refused',
    why: `${target.name} cannot hold ${dropped.name}: the ontology permits no part-of relationship from `
      + `${indefinite(words(target.type))} to ${indefinite(words(dropped.type))}.`,
  }
}
