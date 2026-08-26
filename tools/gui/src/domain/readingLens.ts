/**
 * An ad-hoc reading of a diagram: colour the elements by one attribute, print some attribute values
 * with them.
 *
 * **Momentary by decision.** A lens lasts as long as a reader's visit to a diagram's page. It is not
 * written to the diagram, not saved as a viewpoint, and not kept in browser storage either — the last
 * of those is worth stating because `localStorage` is the obvious place to put it and would quietly
 * turn a situative reading into a preference that follows the reader back. So it lives in component
 * state and dies with the page.
 *
 * Both fields are attribute *names* rather than per-type choices: an attribute is one thing wherever
 * it occurs, so colouring by `risk_score` colours every drawn entity that has one, on one scale. The
 * panel groups its offer by type because *availability* is per type.
 */
export interface ReadingLens {
  /** The attribute to colour by, or `''` for the diagram's authored colours. One at a time: two
   * colourings would each have to win somewhere, and a fill can only be one colour. */
  readonly colourBy: string
  /** Attributes whose values are printed with the element, in the order chosen. */
  readonly printed: readonly string[]
}

export const EMPTY_READING_LENS: ReadingLens = { colourBy: '', printed: [] }

export const isEmptyLens = (lens: ReadingLens): boolean =>
  lens.colourBy === '' && lens.printed.length === 0

/** The lens as query parameters, or `undefined` when there is nothing to ask for.
 *
 * `undefined` rather than an empty record, because a lensless request must reach the *same* address
 * the diagram has always been served from: that address answers from the rendered image on disk, and
 * a stray `?colour_by=` would push every ordinary view through a PlantUML run.
 */
export const lensParams = (
  lens: ReadingLens,
): Readonly<Record<string, string | readonly string[]>> | undefined =>
  isEmptyLens(lens) ? undefined : { colour_by: lens.colourBy, print: lens.printed }
