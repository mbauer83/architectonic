/**
 * What the two document forms — create and edit — answer the same way.
 *
 * They asked it identically and separately: five lines of the same conditional in each, which is
 * the shape a rule takes just before the two copies stop agreeing.
 */

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
