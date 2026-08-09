import { describe, expectTypeOf, it } from 'vitest'
import type { Immutable, SchemaType } from './contractOracle'
import type { components } from './openapi.generated'
import type {
  AreaSchema,
  LiftItemSchema,
  LinkVerdictSchema,
  LayoutSchema,
  LinkSchema,
  NoteGroupSchema,
  NoteSchema,
  ScratchpadLiftSchema,
  ScratchpadListSchema,
  ScratchpadSchema,
  ScratchpadSummarySchema,
} from './scratchpads'

/**
 * Type-level contract assertions for the scratchpad surface.
 *
 * These matter more here than on most surfaces, because the payload *is* the feature: the client
 * reads a document, edits it, and hands the same shape back. A field the decoder does not know is
 * one the round trip drops — a note's body, a link's type — and the loss would be silent, since the
 * server would accept the smaller document as an authoritative replacement of the larger one. The
 * whole-aggregate write turns a decoder gap into data loss rather than a rendering glitch, which is
 * exactly why the two definitions are held equal here rather than trusted to stay so.
 */

describe('a scratchpad, read whole', () => {
  it('decodes the aggregate the read and the replace both answer', () => {
    expectTypeOf<SchemaType<typeof ScratchpadSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ScratchpadResponse']>
    >()
  })

  it('decodes a note, whose only required fields are its id, title and derived area', () => {
    expectTypeOf<SchemaType<typeof NoteSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['NoteWire']>
    >()
  })

  it('decodes a link, typed or not', () => {
    expectTypeOf<SchemaType<typeof LinkSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['LinkWire']>
    >()
  })

  it('decodes the verdict the ontology returns with each link', () => {
    // The client must not narrow this: a verdict kind it does not know would be dropped by the
    // decoder, and the canvas would render a refused link as though nothing were wrong.
    expectTypeOf<SchemaType<typeof LinkVerdictSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['LinkVerdictWire']>
    >()
  })

  it('decodes an area and a note group', () => {
    expectTypeOf<SchemaType<typeof AreaSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AreaWire']>
    >()
    expectTypeOf<SchemaType<typeof NoteGroupSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['GroupWire']>
    >()
  })

  it('decodes the layout block, which is where every coordinate lives', () => {
    // Positional arrays: a rect is `[x, y, w, h]` and a point `[x, y]`. The oracle keeps tuple
    // positions rather than collapsing them, so a decoder that forgot the order would fail here.
    expectTypeOf<SchemaType<typeof LayoutSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['LayoutWire']>
    >()
  })
})

describe('the scratchpad list', () => {
  it('decodes a summary, which carries a count rather than the notes', () => {
    expectTypeOf<SchemaType<typeof ScratchpadSummarySchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ScratchpadSummaryWire']>
    >()
  })

  it('decodes the collection envelope', () => {
    expectTypeOf<SchemaType<typeof ScratchpadListSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ScratchpadListResponse']>
    >()
  })
})

describe('the lift preflight', () => {
  it('decodes the plan and the receipt, which are one answer', () => {
    // The dialog is a report of consequences, so a field the decoder drops is a consequence nobody
    // is shown: a refusal that never renders reads as a lift that will simply work.
    expectTypeOf<SchemaType<typeof ScratchpadLiftSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ScratchpadLiftResponse']>
    >()
  })

  it('decodes each item, including the outcome that decides how it renders', () => {
    expectTypeOf<SchemaType<typeof LiftItemSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['LiftItemWire']>
    >()
  })
})
