import type { AttributeOffer, TypeOffer } from '../../domain/schemas/diagrams'
import type { ReadingLens } from '../../domain/readingLens'
import { CATEGORICAL_PALETTE } from '../../domain/types.generated'

/**
 * The pure part of the reading panel: what each row says, and what a click does to the lens.
 *
 * Separated so the wording and the toggling can be asserted without mounting anything, and because
 * the component is otherwise a list of lists and would carry these inline where they are hard to see.
 */

/** How a row names the thing it is about.
 *
 * A specialization is shown as `type · specialization` rather than on its own: the specialization slug
 * alone ("module", "gateway") does not say what it specialises, and two types can carry slugs that
 * read the same. The bare type keeps its own name with no suffix, because "application-component ·
 * (none)" invents a distinction the model does not make. */
export const typeOfferLabel = (offer: TypeOffer): string =>
  offer.specialization ? `${offer.entity_type} · ${offer.specialization}` : offer.entity_type

/** What a folded row says about what is inside it.
 *
 * Enough to decide whether to unfold: how many attributes there are, and how many are in use. A row
 * with nothing declared says so in words — an empty drawer a reader has to open to find empty is
 * worse than a sentence. */
export const foldSummary = (offer: TypeOffer, lens: ReadingLens): string => {
  const count = offer.attributes.length
  if (count === 0) return 'no attributes declared'
  const shown = offer.attributes.filter(
    (a) => a.name === lens.colourBy || lens.printed.includes(a.name),
  ).length
  const attributes = `${count} attribute${count === 1 ? '' : 's'}`
  return shown === 0 ? attributes : `${attributes}, ${shown} in use`
}

/** Whether this attribute can be offered a colour at all. `none` is the model's answer for free text
 * and lists, and the control is left out rather than disabled-with-a-reason: the reason is that a ramp
 * over prose is meaningless, which the row's declared type already tells a reader. */
export const canTakeColour = (attribute: AttributeOffer): boolean => attribute.colour !== 'none'

/** How many of the drawn entities carry a value, as a row reads it. Zero is stated, not blank: a
 * reader who colours by an attribute nothing carries needs to know that before wondering why the
 * picture did not change. */
export const presenceLabel = (attribute: AttributeOffer): string =>
  attribute.present_on === 0 ? 'no values' : `${attribute.present_on} with values`

/** Colouring is exclusive: one attribute at a time, because a fill can only be one colour. Choosing
 * the attribute already chosen clears it, so the same control both sets and unsets.
 *
 * The control is a **checkbox**, not a radio. A radio is for choosing among the members of a group,
 * and it cannot be unset by clicking the one already chosen — a reader who wanted the authored
 * colours back would need a separate "off" somewhere else on the page. Colouring is not a group
 * either: it is one independent yes/no per attribute that happens to admit at most one yes, and that
 * limit is a fact about a fill rather than a rule about the control. So every row's every option is a
 * checkbox, unchecking a colour is how a reader turns it off, and there is nothing left for a Reset
 * button to do. */
export const withColourBy = (lens: ReadingLens, name: string): ReadingLens => ({
  ...lens,
  colourBy: lens.colourBy === name ? '' : name,
})

/** Printing is not exclusive, and the order a reader chose is kept: the values appear under the
 * element in that order, so re-adding an attribute must not silently move it. */
export const withPrinted = (lens: ReadingLens, name: string): ReadingLens => ({
  ...lens,
  printed: lens.printed.includes(name)
    ? lens.printed.filter((printed) => printed !== name)
    : [...lens.printed, name],
})

/** One step of an attribute's colour mapping: a swatch and what it means.
 *
 * Shown when a colouring is on, because a colour a reader cannot decode is decoration. A ramp gives
 * its two endpoints; a value set gives one step per member, in the declared order the server sent —
 * which is the same order the position in `CATEGORICAL_PALETTE` is taken from, so this key and the
 * picture cannot disagree about which member is which colour. */
export interface ColourStep {
  readonly label: string
  readonly colour: string
  /** The value-set member this step is for, where there is one — what a reader's chosen colour is
   * keyed by. Absent for a gradient end, which is identified by `end` instead. */
  readonly member?: string
  /** Which end of a gradient, where this step is one. `0` is the near end. */
  readonly end?: 0 | 1
}

/** The mapping for the attribute currently coloured by, or `[]` when nothing is.
 *
 * `values` is what makes an ordinal's ramp readable: its enum *is* the scale, so the ends can be
 * named (`negligible → catastrophic`) instead of labelled "low" and "high". A plain number has no
 * declared range and its ends are whatever the diagram happens to hold, so they are named as
 * directions rather than given numbers this panel does not know. */
export const colourKey = (
  attribute: AttributeOffer,
  endpoints: readonly [string, string],
  lens: ReadingLens,
): ColourStep[] => {
  if (attribute.colour === 'palette') {
    return attribute.values.map((member, index) => ({
      label: member,
      member,
      colour: lens.key[member] ?? CATEGORICAL_PALETTE[index % CATEGORICAL_PALETTE.length],
    }))
  }
  if (attribute.colour !== 'ramp') return []
  const named = attribute.declared_type === 'ordinal' && attribute.values.length > 1
  const ends = named
    ? [attribute.values[0], attribute.values[attribute.values.length - 1]]
    : ['lower', 'higher']
  const ramp = lens.ramp ?? endpoints
  return [
    { label: ends[0], colour: ramp[0], end: 0 },
    { label: ends[1], colour: ramp[1], end: 1 },
  ]
}

/** Whether the reader has changed anything about this attribute's colours, so the panel can offer to
 * put them back without offering it when there is nothing to undo. */
export const hasCustomColours = (attribute: AttributeOffer, lens: ReadingLens): boolean =>
  lens.ramp !== null || attribute.values.some((member) => member in lens.key)

/** What the panel header says is happening, so a reader with the panel folded away still knows. */
export const lensSummary = (lens: ReadingLens): string => {
  const parts: string[] = []
  if (lens.colourBy) parts.push(`coloured by ${lens.colourBy}`)
  if (lens.printed.length) parts.push(`printing ${lens.printed.join(', ')}`)
  return parts.join('; ')
}
