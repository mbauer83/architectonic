import type { AttributeOffer, DiagramAttributePanel, TypeOffer } from '../../domain/schemas/diagrams'
import { DEFAULT_GRADIENT, panelOffers, type ReadingLens } from '../../domain/readingLens'

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
 * picture did not change.
 *
 * The wording says *have a value* rather than *with values*, which was read as a count of the
 * attribute's possible values — so a free-text field with five entities filled in looked identical to
 * a five-member enum, and nothing on the row explained why only one of them could be coloured. That
 * question is now answered by `valueSetLabel` beside it. */
export const presenceLabel = (attribute: AttributeOffer): string =>
  attribute.present_on === 0 ? 'none have a value' : `${attribute.present_on} have a value`

/** How many values the attribute may take, where the model bounds them — and nothing at all where it
 * does not.
 *
 * This is the row's answer to "why can I colour that one and not this one". An enum and a free string
 * are both declared `string`, so the declared type alone distinguishes them not at all; the bounded
 * set is exactly what a palette needs and what free text lacks. Absent rather than "unbounded",
 * because a row saying nothing about a value set is the honest shape of "there isn't one". */
export const valueSetLabel = (attribute: AttributeOffer): string =>
  attribute.values.length === 0 ? '' : `${attribute.values.length} values`

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
 * its two endpoints; a value set gives one step per member, in the declared order the server sent,
 * each carrying the colour *the server* gave that member — so this key and the picture cannot
 * disagree about which member is which colour. */
/** What a reader's chosen colour would be keyed by: a member of a value set, or one end of a gradient.
 *
 * A discriminated union rather than two optional fields on one shape. As optionals it was possible to
 * construct a step that was neither, or both, and the handler had to test for each in turn and do
 * nothing if it found neither — a silent no-op where an exhaustive match is available for free. */
export type ColourSubject =
  | { readonly kind: 'member'; readonly member: string }
  | { readonly kind: 'end'; readonly end: 0 | 1 }

export type ColourStep = ColourSubject & {
  readonly label: string
  readonly colour: string
  /** The member a schema declares as its default: what a reader sees on an element nobody has
   * assessed. It takes no place on the scale, so a control can set it apart from the graded ones. */
  readonly unset?: boolean
}

/** What an unset member is coloured, and the one colour no gradient reaches. */
export const UNSET_MEMBER_COLOUR = '#ffffff' 

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
    // The server's answer for the gradient in effect, not a second derivation of it. The swatches
    // are the key to the picture, so deriving them here would be two chances to disagree about one
    // colouring — and the gradients' stops live in the ontology's own module, not in the browser.
    const graded = attribute.colour_by_gradient?.[lens.gradient ?? DEFAULT_GRADIENT] ?? {}
    return attribute.values.map((member) => ({
      kind: 'member' as const,
      member,
      label: member,
      colour: lens.key[member] ?? graded[member] ?? UNSET_MEMBER_COLOUR,
      unset: member === attribute.unset_value,
    }))
  }
  if (attribute.colour !== 'ramp') return []
  const named = attribute.declared_type === 'ordinal' && attribute.values.length > 1
  const ends = named
    ? [attribute.values[0], attribute.values[attribute.values.length - 1]]
    : ['lower', 'higher']
  const ramp = lens.ramp ?? endpoints
  return [
    { kind: 'end', end: 0, label: ends[0], colour: ramp[0] },
    { kind: 'end', end: 1, label: ends[1], colour: ramp[1] },
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
  if (lens.legend) parts.push('explaining the notation')
  return parts.join('; ')
}

/** What this diagram can be adjusted by, said while nothing is adjusted yet.
 *
 * Not a constant, because the panel does not always offer the same things: a diagram whose types
 * declare no attributes still has notation a legend can explain, and greeting its reader with
 * "colour and print by attribute" advertises the one control it does not have.
 *
 * Off `panelOffers`, which is also what decides whether this panel is drawn at all — so the header
 * cannot name a control the panel withheld, or fall silent while one is on screen.
 */
export const panelHint = (panel: DiagramAttributePanel | null): string => {
  const offers = panelOffers(panel)
  const said = [
    ...(offers.attributes ? ['colour and print by attribute'] : []),
    ...(offers.legend ? ['explain the notation'] : []),
  ]
  return said.join(', ')
}
