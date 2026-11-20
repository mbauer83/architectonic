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

/** The types an attribute its schema does not declare may be given — the entity form's five. */
export const AD_HOC_TYPES = ['string', 'integer', 'number', 'boolean', 'array'] as const
export type AdHocType = typeof AD_HOC_TYPES[number]

/** The type an undeclared attribute's value was written as. */
export function adHocTypeOf(value: unknown): AdHocType {
  if (typeof value === 'boolean') return 'boolean'
  if (typeof value === 'number') return Number.isInteger(value) ? 'integer' : 'number'
  return Array.isArray(value) ? 'array' : 'string'
}

/**
 * A typed input's cell as the value an undeclared attribute stores.
 *
 * A declared attribute stores its cell and the schema says how to read it. An undeclared one has
 * no schema, so the value itself carries the type: a lift states it beside the entity's
 * properties from what the value is. A cell that cannot be read as the chosen type stays text
 * rather than becoming a different value than was typed.
 */
export function adHocValue(type: AdHocType, cell: string): unknown {
  if (type === 'boolean') return cell === 'true'
  if (type === 'integer' || type === 'number') {
    const parsed = Number(cell)
    const readable = cell.trim() !== '' && Number.isFinite(parsed)
      && (type === 'number' || Number.isInteger(parsed))
    return readable ? parsed : cell
  }
  if (type === 'array') {
    try {
      const parsed: unknown = JSON.parse(cell)
      return Array.isArray(parsed) ? parsed : cell
    } catch {
      return cell
    }
  }
  return cell
}

/** Why *name* cannot be added as a new attribute, or `null` when it can.
 *
 * A name is one line, because it is a cell of the entity's Properties table; and it is new,
 * because an attribute the note or its schema already has is edited in its own row. */
export function attributeNameProblem(name: string, rows: readonly AttributeRow[]): string | null {
  const trimmed = name.trim()
  if (!trimmed) return 'Give the attribute a name.'
  if (/[\r\n]/.test(name)) return 'An attribute name is one line.'
  return rows.some((row) => row.name === trimmed)
    ? `'${trimmed}' is already listed above.`
    : null
}

/** Set one attribute on a note. An empty or absent value removes the key, and the last key removed
 * removes the block: the wire shape is optional-key, so "not set" is said by absence. */
export function withAttribute(
  scratchpad: Scratchpad, noteId: string, name: string, value: unknown,
): Scratchpad {
  const note = (scratchpad.notes ?? []).find((candidate) => candidate.id === noteId)
  if (!note) return scratchpad
  const attributes: Record<string, unknown> = { ...note.attributes }
  if (value === '' || value === undefined || value === null) delete attributes[name]
  else attributes[name] = value
  return withNote(
    scratchpad,
    Object.keys(attributes).length ? { ...note, attributes } : without(note, 'attributes'),
  )
}
