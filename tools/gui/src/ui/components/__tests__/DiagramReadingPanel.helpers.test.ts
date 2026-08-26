import { describe, expect, it } from 'vitest'
import {
  canTakeColour, colourKey, foldSummary, hasCustomColours, lensSummary, presenceLabel, typeOfferLabel,
  withColourBy, withPrinted,
} from '../DiagramReadingPanel.helpers'
import { CATEGORICAL_PALETTE } from '../../../domain/types.generated'
import {
  EMPTY_READING_LENS, isEmptyLens, lensParams, withDeclaredColours, withRampEnd, type ReadingLens,
} from '../../../domain/readingLens'
import type { AttributeOffer, TypeOffer } from '../../../domain/schemas/diagrams'

const attribute = (over: Partial<AttributeOffer> = {}): AttributeOffer => ({
  name: 'risk_score', declared_type: 'integer', colour: 'ramp', values: [], present_on: 3, ...over,
})

/** A lens literal, so a test states only the part it is about. */
const lens = (over: Partial<ReadingLens> = {}): ReadingLens => ({ ...EMPTY_READING_LENS, ...over })

const offer = (over: Partial<TypeOffer> = {}): TypeOffer => ({
  entity_type: 'application-component', specialization: '', drawn: 4, attributes: [attribute()], ...over,
})

describe('what a row says', () => {
  it('names a bare type with no suffix', () => {
    expect(typeOfferLabel(offer())).toBe('application-component')
  })

  it('names a specialization together with what it specialises', () => {
    // The slug alone does not say what it specialises, and two types can carry slugs that read alike.
    expect(typeOfferLabel(offer({ specialization: 'module' }))).toBe('application-component · module')
  })

  it('says in words that a type declares nothing rather than offering an empty drawer', () => {
    expect(foldSummary(offer({ attributes: [] }), EMPTY_READING_LENS)).toBe('no attributes declared')
  })

  it('counts the attributes and, separately, the ones in use', () => {
    const row = offer({ attributes: [attribute(), attribute({ name: 'owner', colour: 'none' })] })

    expect(foldSummary(row, EMPTY_READING_LENS)).toBe('2 attributes')
    expect(foldSummary(row, lens({ colourBy: 'risk_score', printed: ['owner'] }))).toBe('2 attributes, 2 in use')
  })

  it('states an absence of values rather than leaving the row blank', () => {
    expect(presenceLabel(attribute({ present_on: 0 }))).toBe('no values')
    expect(presenceLabel(attribute({ present_on: 1 }))).toBe('1 with values')
  })

  it('offers no colour where the model declares neither an order nor a bounded set', () => {
    expect(canTakeColour(attribute({ colour: 'ramp' }))).toBe(true)
    expect(canTakeColour(attribute({ colour: 'palette' }))).toBe(true)
    expect(canTakeColour(attribute({ colour: 'none' }))).toBe(false)
  })
})

describe('what a click does', () => {
  it('replaces the colouring rather than adding to it', () => {
    // A fill can only be one colour, so this is exclusive across the whole panel.
    const after = withColourBy(lens({ colourBy: 'risk_score', printed: [] }), 'severity')

    expect(after.colourBy).toBe('severity')
  })

  it('clears the colouring when the chosen attribute is chosen again', () => {
    // The same control sets and unsets, so getting the authored colours back needs no separate "off".
    expect(withColourBy(lens({ colourBy: 'risk_score', printed: [] }), 'risk_score').colourBy).toBe('')
  })

  it('keeps the order attributes were chosen to print in', () => {
    const after = withPrinted(withPrinted(EMPTY_READING_LENS, 'owner'), 'risk_score')

    expect(after.printed).toEqual(['owner', 'risk_score'])
  })

  it('removes a printed attribute without disturbing the others', () => {
    const current = lens({ colourBy: '', printed: ['a', 'b', 'c'] })

    expect(withPrinted(current, 'b').printed).toEqual(['a', 'c'])
  })

  it('leaves the printed order alone when an attribute is re-added', () => {
    const current = lens({ colourBy: '', printed: ['a', 'b'] })

    expect(withPrinted(withPrinted(current, 'a'), 'a').printed).toEqual(['b', 'a'])
  })

  it('does not confuse colouring with printing', () => {
    const after = withColourBy(lens({ colourBy: '', printed: ['owner'] }), 'risk_score')

    expect(after.printed).toEqual(['owner'])
  })
})

describe('the colour key a colouring unfolds', () => {
  const ends: readonly [string, string] = ['#fbbf24', '#dc2626']

  it('gives a plain number two ends named as directions', () => {
    // The ends are whatever this diagram happens to hold, and the panel is not told the numbers.
    expect(colourKey(attribute(), ends, EMPTY_READING_LENS)).toEqual([
      { label: 'lower', colour: '#fbbf24', end: 0 },
      { label: 'higher', colour: '#dc2626', end: 1 },
    ])
  })

  it("names an ordinal's ends from its declared scale", () => {
    // An ordinal's enum *is* the scale, so the ends have names and "low"/"high" would hide them.
    const severity = attribute({
      declared_type: 'ordinal',
      values: ['negligible', 'minor', 'major', 'catastrophic'],
    })

    expect(colourKey(severity, ends, EMPTY_READING_LENS).map((step) => step.label)).toEqual(['negligible', 'catastrophic'])
  })

  it('gives an unordered value set one swatch per member, in the declared order', () => {
    const lifecycle = attribute({ colour: 'palette', values: ['planned', 'active', 'retired'] })

    expect(colourKey(lifecycle, ends, EMPTY_READING_LENS)).toEqual([
      { label: 'planned', member: 'planned', colour: CATEGORICAL_PALETTE[0] },
      { label: 'active', member: 'active', colour: CATEGORICAL_PALETTE[1] },
      { label: 'retired', member: 'retired', colour: CATEGORICAL_PALETTE[2] },
    ])
  })

  it('cycles the palette rather than running out of colours', () => {
    const many = attribute({
      colour: 'palette',
      values: Array.from({ length: CATEGORICAL_PALETTE.length + 1 }, (_v, i) => `m${i}`),
    })

    const steps = colourKey(many, ends, EMPTY_READING_LENS)
    expect(steps).toHaveLength(CATEGORICAL_PALETTE.length + 1)
    expect(steps[steps.length - 1].colour).toBe(CATEGORICAL_PALETTE[0])
  })

  it('has no key for an attribute no colour can read', () => {
    expect(colourKey(attribute({ colour: 'none' }), ends, EMPTY_READING_LENS)).toEqual([])
  })
})

describe('the colours a reader chooses for themselves', () => {
  const ends: readonly [string, string] = ['#fbbf24', '#dc2626']

  it("shows a member's chosen colour in place of its declared one", () => {
    const lifecycle = attribute({ colour: 'palette', values: ['planned', 'active'] })
    const chosen = lens({ colourBy: 'lifecycle', key: { active: '#111111' } })

    expect(colourKey(lifecycle, ends, chosen).map((step) => step.colour))
      .toEqual([CATEGORICAL_PALETTE[0], '#111111'])
  })

  it('leaves every other member on its declared colour', () => {
    // Partial by design: changing one colour must not mean restating the rest.
    const lifecycle = attribute({ colour: 'palette', values: ['a', 'b', 'c'] })
    const chosen = lens({ key: { b: '#111111' } })

    expect(colourKey(lifecycle, ends, chosen).map((step) => step.colour))
      .toEqual([CATEGORICAL_PALETTE[0], '#111111', CATEGORICAL_PALETTE[2]])
  })

  it("shows a chosen gradient in place of the declared endpoints", () => {
    const chosen = lens({ colourBy: 'risk_score', ramp: ['#000000', '#ffffff'] })

    expect(colourKey(attribute(), ends, chosen).map((step) => step.colour))
      .toEqual(['#000000', '#ffffff'])
  })

  it('changes one end of a gradient against the declared other end', () => {
    // The first adjustment has no gradient to build on, so it starts from what is declared —
    // otherwise the untouched end would come back as undefined and the ramp would be half a request.
    const after = withRampEnd(EMPTY_READING_LENS, 1, '#ffffff', ends)

    expect(after.ramp).toEqual(['#fbbf24', '#ffffff'])
  })

  it('sends the mapping only for what is being coloured by', () => {
    const chosen = lens({ colourBy: 'lifecycle', ramp: ['#000000', '#ffffff'], key: { a: '#111111' } })

    expect(lensParams(chosen)).toEqual({
      colour_by: 'lifecycle', print: [], ramp: '#000000:#ffffff', key: ['a:#111111'],
    })
  })

  it('sends no mapping when the reader has customised nothing', () => {
    expect(lensParams(lens({ colourBy: 'risk_score' }))).toEqual({ colour_by: 'risk_score', print: [] })
  })

  it('offers to put back the declared colours only once something was changed', () => {
    const lifecycle = attribute({ colour: 'palette', values: ['a', 'b'] })

    expect(hasCustomColours(lifecycle, EMPTY_READING_LENS)).toBe(false)
    expect(hasCustomColours(lifecycle, lens({ key: { a: '#111111' } }))).toBe(true)
    expect(hasCustomColours(lifecycle, lens({ ramp: ['#000000', '#ffffff'] }))).toBe(true)
  })

  it("puts back one attribute's declared colours without touching another's", () => {
    const chosen = lens({ key: { a: '#111111', other: '#222222' } })

    expect(withDeclaredColours(chosen, ['a']).key).toEqual({ other: '#222222' })
    expect(withDeclaredColours(chosen, ['a']).ramp).toBeNull()
  })
})

describe('what the folded header reports', () => {
  it('says nothing when nothing is asked for', () => {
    expect(lensSummary(EMPTY_READING_LENS)).toBe('')
  })

  it('reports both halves of a reading', () => {
    expect(lensSummary(lens({ colourBy: 'risk_score', printed: ['owner', 'tier'] })))
      .toBe('coloured by risk_score; printing owner, tier')
  })
})

describe('the lens as a request', () => {
  it('asks for nothing at all when it is empty', () => {
    // Not an empty record: a lensless request must reach the address that answers from the rendered
    // image on disk, and a stray `?colour_by=` would push every ordinary view through PlantUML.
    expect(lensParams(EMPTY_READING_LENS)).toBeUndefined()
    expect(isEmptyLens(EMPTY_READING_LENS)).toBe(true)
  })

  it('sends printed attributes as a repeated key rather than one joined value', () => {
    // The route declares `list[str]`, which reads repeated keys; a joined value arrives as one
    // member named "a,b".
    expect(lensParams(lens({ colourBy: 'risk_score', printed: ['a', 'b'] })))
      .toEqual({ colour_by: 'risk_score', print: ['a', 'b'] })
  })

  it('is a request when only printing is asked for', () => {
    expect(lensParams(lens({ colourBy: '', printed: ['owner'] }))).toEqual({ colour_by: '', print: ['owner'] })
  })
})
