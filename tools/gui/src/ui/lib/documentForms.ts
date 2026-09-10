/**
 * What the two document forms — create and edit — answer the same way.
 *
 * They asked these identically and separately, which is the shape a rule takes just before its
 * copies stop agreeing. One is about when to complain; the other is the lookup that decides which
 * sections, connections and extra fields a form offers at all.
 */

import type { DocumentType } from '../../domain'

/** The declared type a document is of, or null while the catalogue has not arrived. */
export const documentTypeFor = (
  types: readonly DocumentType[], docType: string | undefined,
): DocumentType | null => types.find((type) => type.doc_type === docType) ?? null

/**
 * The title error to show, or null while there is nothing to complain about yet.
 *
 * Silent until the author has either left the field or tried to submit. Complaining about an empty
 * title the moment a form opens tells someone off for not having typed yet.
 */
export const titleErrorFor = (
  title: string, touched: boolean, attempted: boolean,
): string | null =>
  (!title.trim() && (touched || attempted)) ? 'Title is required.' : null

/**
 * The entity types worth suggesting for the section the cursor sits in.
 *
 * One question rather than three chained derivations at the view: which section, which spec, which
 * terms. The chain is the mechanism; the answer is what a picker needs.
 */
export const suggestedTypesForCursorSection = (
  body: string,
  sections: unknown,
  at: (body: string, offset: number) => string | null,
  specOf: (sections: unknown, name: string | null) => unknown,
  termsOf: (spec: unknown) => readonly string[],
  offset: number,
): readonly string[] => termsOf(specOf(sections, at(body, offset)))
