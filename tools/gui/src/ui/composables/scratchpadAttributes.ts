import type { Scratchpad } from '../../domain/schemas/scratchpads'
import { withNote, without } from './scratchpadEdits'

/**
 * A note's attributes, as the rows an editor shows and the edit it makes.
 *
 * Apart from the component so the two decisions here are testable without one: which attributes
 * are offered — everything the schema declares, then whatever else the note already holds — and
 * what clearing a value means, which is removing the key rather than storing an empty one.
 */

export interface AttributeRow {
  readonly name: string
  /** The note's value, or `undefined` for a declared attribute it has not set. */
  readonly value: unknown
  /** Whether the schema declares it. One it does not is carried as an ad-hoc property. */
  readonly declared: boolean
}

/** The schema's attributes in declared order, then the note's own that the schema does not know. */
export function attributeRows(
  attributes: Readonly<Record<string, unknown>>, declared: readonly string[],
): AttributeRow[] {
  const known = new Set(declared)
  return [
    ...declared.map((name) => ({ name, value: attributes[name], declared: true })),
    ...Object.keys(attributes)
      .filter((name) => !known.has(name))
      .sort()
      .map((name) => ({ name, value: attributes[name], declared: false })),
  ]
}

/** A value as the text a typed input edits: the property cell an entity would store it in.
 *
 * An agent may have written a number, a boolean or a list; the inputs speak the cell form the
 * entity forms already use, in which a list is compact JSON. */
export function attributeCell(value: unknown): string {
  if (value === undefined || value === null) return ''
  return typeof value === 'string' ? value : JSON.stringify(value)
}

/** Set one attribute on a note. An empty value removes the key, and the last key removed removes
 * the block: the wire shape is optional-key, so "not set" is said by absence. */
export function withAttribute(
  scratchpad: Scratchpad, noteId: string, name: string, value: string,
): Scratchpad {
  const note = (scratchpad.notes ?? []).find((candidate) => candidate.id === noteId)
  if (!note) return scratchpad
  const attributes: Record<string, unknown> = { ...note.attributes }
  if (value === '') delete attributes[name]
  else attributes[name] = value
  return withNote(
    scratchpad,
    Object.keys(attributes).length ? { ...note, attributes } : without(note, 'attributes'),
  )
}
