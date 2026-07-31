import { Schema } from 'effect'
import { describe, expectTypeOf, it } from 'vitest'
import type { Immutable, SchemaType } from './contractOracle'
import type { components } from './openapi.generated'
import { EntitySummarySchema } from './entities'

/**
 * That the contract check can tell `null` from absent — the property the rest of the checking rests
 * on, and the one it did not have.
 *
 * A closed server DTO fills an unset optional with `null`; the handlers it replaced omitted the key.
 * `Schema.optional(X)` accepts absent-or-value and rejects `null`, so the difference decides whether
 * a row decodes or is silently dropped — it cost five browser specs and rendered an empty entity
 * list with nothing logged. `contracts:check` passed throughout, because the *document* claimed
 * `host_diagram_id?: string | null` for a route that can never send null: the oracle admitted both,
 * so no assertion against it could discriminate, and the only way to satisfy one would have been to
 * widen the decoder to accept a null the server never sends.
 *
 * The document now states the route's serialisation policy (`NullsOmitted`, stripped from the
 * schema by `apply_wire_null_policy`), so the oracle is exact. These assertions are the evidence
 * that exactness is enough: with a truthful oracle, plain type equality separates all three cases,
 * and no cross-language runtime fixture is needed to catch this class.
 */

// ── The three cases, as the oracle expresses them ────────────────────────────

/** The server omits the key. What `response_model_exclude_none=True` produces. */
type Omitted = { key?: string }
/** The server always sends the key, sometimes as null. */
type AlwaysNullable = { key: string | null }
/** The server may omit it *or* send null — the permissive default. */
type EitherWay = { key?: string | null }

const OptionalSchema = Schema.Struct({ key: Schema.optional(Schema.String) })
const NullOrSchema = Schema.Struct({ key: Schema.NullOr(Schema.String) })
const OptionalNullOrSchema = Schema.Struct({ key: Schema.optional(Schema.NullOr(Schema.String)) })

describe('null versus absent, at the type level', () => {
  it('matches each decoder to the wire shape it actually accepts', () => {
    expectTypeOf<SchemaType<typeof OptionalSchema>>().toEqualTypeOf<Immutable<Omitted>>()
    expectTypeOf<SchemaType<typeof NullOrSchema>>().toEqualTypeOf<Immutable<AlwaysNullable>>()
    expectTypeOf<SchemaType<typeof OptionalNullOrSchema>>().toEqualTypeOf<Immutable<EitherWay>>()
  })

  it('separates all three, so no pairing survives by accident', () => {
    // Without these, the assertions above could pass under a comparison that ignored optionality or
    // collapsed `null` into `undefined` — and the check would go on certifying the defect.
    expectTypeOf<SchemaType<typeof OptionalSchema>>().not.toEqualTypeOf<Immutable<AlwaysNullable>>()
    expectTypeOf<SchemaType<typeof OptionalSchema>>().not.toEqualTypeOf<Immutable<EitherWay>>()
    expectTypeOf<SchemaType<typeof NullOrSchema>>().not.toEqualTypeOf<Immutable<Omitted>>()
    expectTypeOf<SchemaType<typeof NullOrSchema>>().not.toEqualTypeOf<Immutable<EitherWay>>()
    expectTypeOf<SchemaType<typeof OptionalNullOrSchema>>().not.toEqualTypeOf<Immutable<Omitted>>()
    expectTypeOf<SchemaType<typeof OptionalNullOrSchema>>().not.toEqualTypeOf<Immutable<AlwaysNullable>>()
  })
})

// ── The defect itself, held against the real document ────────────────────────

describe('the published document states what the wire carries', () => {
  it('publishes an entity row’s optionals as absent-or-value, never null', () => {
    // The field the defect was found on. `| null` here is the document lying about a route that
    // serialises with `exclude_none`, and it is what let the decode failure through.
    expectTypeOf<components['schemas']['EntitySummary']['host_diagram_id']>().toEqualTypeOf<
      string | undefined
    >()
    expectTypeOf<components['schemas']['EntitySummary']['conn_in']>().toEqualTypeOf<
      number | undefined
    >()
    expectTypeOf<components['schemas']['EntitySummary']['last_updated']>().toEqualTypeOf<
      string | undefined
    >()
  })

  it('agrees with the decoder the entity list is read through', () => {
    // Only the fields the document declares: `EntitySummarySchema` is shared with the diagram
    // entity list, whose rows carry hierarchy and alias keys this operation does not return.
    // Reconciling that sharing is the per-DTO contract work; the fields below are the ones this
    // policy governs, and they must agree now.
    type Row = SchemaType<typeof EntitySummarySchema>
    expectTypeOf<Row['host_diagram_id']>().toEqualTypeOf<
      components['schemas']['EntitySummary']['host_diagram_id']
    >()
    expectTypeOf<Row['conn_in']>().toEqualTypeOf<components['schemas']['EntitySummary']['conn_in']>()
  })

  it('publishes a page cursor as present-and-nullable, because that is the convention', () => {
    // The opposite direction: `next_cursor` is null on the last page rather than absent, so a
    // policy applied blanket-fashion would have broken this decode instead of fixing anything.
    expectTypeOf<components['schemas']['AnalysisNodePageResponse']['next_cursor']>().toEqualTypeOf<
      string | null
    >()
  })
})
