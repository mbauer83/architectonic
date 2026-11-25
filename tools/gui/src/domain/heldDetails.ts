/**
 * An element's details as something other than the model holds them — a candidate architecture, say —
 * laid over what the model holds, and the fields where that differs from what it stands on. The entity
 * form opens on the first and marks the second, so an edit is made on what is actually there.
 */
import type { EntityDetail } from './index'

/** An element's fields as held, by field name, as a composed view states them. */
export type HeldFields = Readonly<Record<string, unknown>>

/** One field that differs from what the holder stands on, and the value it has there. */
export interface DifferingField {
  readonly field: string
  readonly beneath: unknown
}

const text = (value: unknown, otherwise: string | undefined): string | undefined =>
  typeof value === 'string' ? value : otherwise
const texts = (value: unknown, otherwise: readonly string[]): readonly string[] =>
  Array.isArray(value) ? value.map(String) : otherwise
const record = (value: unknown, otherwise: EntityDetail['properties']): EntityDetail['properties'] =>
  typeof value === 'object' && value !== null && !Array.isArray(value)
    ? Object.fromEntries(Object.entries(value)) : otherwise

/** *detail* with the fields *held* states laid over it; a field *held* does not state stays as the model has it. */
export const withHeldDetails = (detail: EntityDetail, held: HeldFields): EntityDetail => ({
  ...detail,
  name: text(held.name, detail.name) ?? detail.name,
  status: text(held.status, detail.status) ?? detail.status,
  summary: text(held.summary, detail.summary),
  notes: text(held.notes, detail.notes),
  group: text(held.group, detail.group),
  keywords: [...texts(held.keywords, detail.keywords)],
  specializations: [...texts(held.specializations, detail.specializations)],
  properties: record(held.properties, detail.properties),
})

/** A field's value as a line of text, for saying what it is beneath. */
export const shownValue = (value: unknown): string => {
  if (value === null || value === undefined || value === '') return '—'
  if (Array.isArray(value)) return value.length ? value.map(String).join(', ') : '—'
  return typeof value === 'object' ? JSON.stringify(value) : String(value)
}
