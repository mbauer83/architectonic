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
  /** The reader's own gradient for a continuous attribute, as two `#rrggbb` colours, or `null` for
   * the declared endpoints. Two readers colouring by two different attributes are not obliged to
   * want the same two colours, and neither should have to author a rule to say so. */
  readonly ramp: readonly [string, string] | null
  /** The reader's own colour for individual members of a value set. **Partial**: a member absent here
   * keeps the colour its declared position gives it, so changing one does not mean restating the
   * rest — and a reader who has customised nothing sends nothing. */
  readonly key: Readonly<Record<string, string>>
  /** Which marks the diagram should explain about itself. A legend goes *into* the image, so asking
   * for one is asking for a different picture — which is why it makes the request non-empty on its
   * own, where a colour mapping does not. */
  readonly legends: readonly LegendMark[]
}

/** The marks a diagram can explain. Each toggles independently, because a reader asking what the
 * colours mean is asking a different question from what the arrows mean — and one drawn element
 * carries all of its marks at once, which is why the legend is a table and not sample elements. */
export const LEGEND_MARKS = ['colour', 'shape', 'glyph', 'arrow'] as const
export type LegendMark = (typeof LEGEND_MARKS)[number]

/** What each mark's legend tells a reader, for the checkbox label's tooltip. */
export const LEGEND_MARK_MEANING: Readonly<Record<LegendMark, string>> = {
  colour: 'What the fills mean — the element kinds, or the attribute being coloured by',
  shape: 'What the corner shapes mean',
  glyph: 'What the icons mean',
  arrow: 'Which relationship each line is, and how it is drawn',
}

export const EMPTY_READING_LENS: ReadingLens = {
  colourBy: '', printed: [], ramp: null, key: {}, legends: [],
}

/** Whether this asks for anything.
 *
 * A mapping alone asks for nothing: it says *how* to colour, and without `colourBy` there is nothing
 * to colour. So a mapping a reader adjusted and then switched off cannot keep forcing re-renders. */
export const isEmptyLens = (lens: ReadingLens): boolean =>
  lens.colourBy === '' && lens.printed.length === 0 && lens.legends.length === 0

/** The lens as query parameters, or `undefined` when there is nothing to ask for.
 *
 * `undefined` rather than an empty record, because a lensless request must reach the *same* address
 * the diagram has always been served from: that address answers from the rendered image on disk, and
 * a stray `?colour_by=` would push every ordinary view through a PlantUML run.
 *
 * A member's colour travels as `member:#rrggbb`, split by the server at the **last** colon so a
 * member containing one survives. The mapping is only sent for the attribute being coloured by:
 * carrying every attribute's customisation on every request would put a reader's whole history of
 * adjustments into the URL of one picture.
 */
export const lensParams = (
  lens: ReadingLens,
): Readonly<Record<string, string | readonly string[]>> | undefined => {
  if (isEmptyLens(lens)) return undefined
  // Only what was asked for. Sending `colour_by=` empty alongside a legend request put a parameter
  // in the URL that says nothing — harmless, since the server strips it, and still a URL that
  // misdescribes the request it carries.
  const params: Record<string, string | readonly string[]> = {}
  if (lens.colourBy) params.colour_by = lens.colourBy
  if (lens.printed.length) params.print = lens.printed
  if (lens.ramp) params.ramp = `${lens.ramp[0]}:${lens.ramp[1]}`
  const key = Object.entries(lens.key).map(([member, colour]) => `${member}:${colour}`)
  if (key.length) params.key = key
  if (lens.legends.length) params.legend = lens.legends
  return params
}

/** Turn one mark's legend on or off. The order is the declared one rather than the click order: the
 * legend's sections are laid out in a fixed order, and a reader who unchecks and rechecks a mark
 * should not find their legend rearranged. */
export const withLegendMark = (lens: ReadingLens, mark: LegendMark): ReadingLens => ({
  ...lens,
  legends: lens.legends.includes(mark)
    ? lens.legends.filter((existing) => existing !== mark)
    : LEGEND_MARKS.filter((candidate) => candidate === mark || lens.legends.includes(candidate)),
})

/** The reader's colour for one member, or the declared one they have not overridden. */
export const withMemberColour = (lens: ReadingLens, member: string, colour: string): ReadingLens => ({
  ...lens,
  key: { ...lens.key, [member]: colour },
})

/** The reader's gradient, one end at a time. `from` is the near end. */
export const withRampEnd = (
  lens: ReadingLens,
  end: 0 | 1,
  colour: string,
  declared: readonly [string, string],
): ReadingLens => {
  const current = lens.ramp ?? declared
  return { ...lens, ramp: end === 0 ? [colour, current[1]] : [current[0], colour] }
}

/** Forget every customisation for the attribute being coloured by, back to the declared colours.
 *
 * Per-colouring rather than global: a reader who adjusted a gradient and wants the declared one back
 * should not lose the member colours they set on a different attribute. */
export const withDeclaredColours = (lens: ReadingLens, members: readonly string[]): ReadingLens => ({
  ...lens,
  ramp: null,
  key: Object.fromEntries(Object.entries(lens.key).filter(([member]) => !members.includes(member))),
})
