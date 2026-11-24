/**
 * What a canvas marks over a drawn diagram, by element: a candidate's comparison with its base
 * (+ added, ~ changed, − removed, drawn as a faded dashed ghost), and what a row or a choice is about.
 * A reader of the canvas may add marks of its own kind (a stress analysis marks what a stressor hits).
 * Marks annotate; nothing is filled or recoloured.
 */
import type { ChangeDifference, ConnectionKey } from '../schemas/candidates'
import { stableEntityId } from '../artifactId'

export type MarkKind = 'hit' | 'added' | 'edited' | 'removed' | 'framed'

export interface CanvasMark {
  readonly kind: MarkKind
  /** The short tag beside the element, such as `hit by 2 of 3` or `+`. */
  readonly tag: string
  readonly title: string
}

/** Marks by stable entity id: how a drawing's key and a model id meet (`stableEntityId`). */
export type Marks = ReadonlyMap<string, CanvasMark>

const DIFF_KIND: Readonly<Record<string, MarkKind>> = { added: 'added', edited: 'edited', removed: 'removed' }
const DIFF_TAG: Readonly<Record<string, string>> = { added: '+', edited: '~', removed: '−' }
const DIFF_WORD: Readonly<Record<string, string>> = {
  added: 'Added', edited: 'Changed: a field differs from the base', removed: 'Removed',
}

const isConnection = (target: string | ConnectionKey): target is ConnectionKey => typeof target !== 'string'

/** The elements a comparison changed, marked as it changed them; a changed relation marks neither end. */
export const diffMarks = (diff: readonly ChangeDifference[]): Marks =>
  new Map(diff.flatMap((row) => {
    const kind = DIFF_KIND[row.change]
    if (!kind || isConnection(row.target)) return []
    const changed = Object.keys(row.fields)
    const title = kind === 'edited' ? `${DIFF_WORD[kind]} (${changed.join(', ')})` : DIFF_WORD[kind]
    return [[stableEntityId(row.target), { kind, tag: DIFF_TAG[kind], title }] as const]
  }))

/** What a row, a hint or a choice is about, framed so it can be found on the picture. */
export const framedMarks = (ids: Iterable<string>, title: string): Marks =>
  new Map([...ids].map((id) => [stableEntityId(id), { kind: 'framed' as const, tag: '', title }]))
