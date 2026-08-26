/** One row of a "where does this appear" list: where it goes, what it is called, what qualifies it.
 *
 * Its own module because both sides need it and neither should own it: `EntityReferenceList` draws a
 * row and `EntityDetailView.references` builds one, and a type exported from a `.vue` file is not
 * importable as a type. Keeping it here is also what stops the generic list from importing a view.
 */
export interface EntityReferenceRow {
  /** Stable within the list. Composed by the caller, because what makes a row unique is the caller's
   * question — a document is identified by document, section and href together. */
  readonly key: string
  readonly to: string
  readonly name: string
  /** Shown after the name when non-empty. Empty means the row has nothing to qualify it, not that
   * something is missing. */
  readonly meta: string
}
