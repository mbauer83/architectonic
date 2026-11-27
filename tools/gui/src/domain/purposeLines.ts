/**
 * Purpose lines — who a view is for and what it answers — as the GUI reads and edits them.
 *
 * The wire shape is `schemas/purposeLines.ts`; this is what a view does with it: tell a reference from
 * prose, add and remove entries without duplicating one, and say a shown line in words.
 */
import type { DiagramPurpose, PurposeEntry, PurposeEntryShown } from './schemas/purposeLines'

export type { DiagramPurpose, PurposeEntry, PurposeEntryShown }

/** The two lists a purpose line holds, named by their stored keys. */
export type PurposeList = 'stakeholders' | 'concerns'

/** The id a reference names, or undefined for prose. */
export const referencedId = (entry: PurposeEntry): string | undefined =>
  typeof entry === 'string' ? undefined : entry.ref

const sameEntry = (a: PurposeEntry, b: PurposeEntry): boolean =>
  typeof a === 'string' || typeof b === 'string' ? a === b : a.ref === b.ref

/** A stored list read as entries: prose strings and `{ref}` mappings, anything else dropped. */
export const purposeEntries = (raw: unknown): PurposeEntry[] =>
  Array.isArray(raw)
    ? raw.flatMap((item: unknown): PurposeEntry[] => {
      if (typeof item === 'string') return [item]
      return typeof item === 'object' && item !== null && 'ref' in item && typeof item.ref === 'string'
        ? [{ ref: item.ref }]
        : []
    })
    : []

/** *entries* with *entry* appended, unless it is empty prose or already there. */
export function withEntry(entries: readonly PurposeEntry[], entry: PurposeEntry): PurposeEntry[] {
  const cleaned = typeof entry === 'string' ? entry.trim() : entry
  if (cleaned === '' || entries.some((existing) => sameEntry(existing, cleaned))) return [...entries]
  return [...entries, cleaned]
}

/** *entries* without the one at *index*. */
export const withoutEntry = (entries: readonly PurposeEntry[], index: number): PurposeEntry[] =>
  entries.filter((_, position) => position !== index)

/** Whether a shown line says anything. */
export const statesPurpose = (purpose: DiagramPurpose | undefined): purpose is DiagramPurpose =>
  purpose !== undefined && (purpose.stakeholders.length > 0 || purpose.concerns.length > 0)

/** A shown list as one phrase: `Operations, Warehouse staff`. */
export const listedText = (entries: readonly PurposeEntryShown[]): string =>
  entries.map((entry) => entry.text).join(', ')

/** The whole line in words, for a caption or a title attribute: `For A, B · Answers C`. */
export function purposeSentence(purpose: DiagramPurpose): string {
  const parts = [
    purpose.stakeholders.length > 0 ? `For ${listedText(purpose.stakeholders)}` : '',
    purpose.concerns.length > 0 ? `Answers ${listedText(purpose.concerns)}` : '',
  ]
  return parts.filter((part) => part !== '').join(' · ')
}
