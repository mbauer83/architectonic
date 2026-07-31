import { describe, expectTypeOf, it } from 'vitest'
import type { Immutable, SchemaType } from './contractOracle'
import type { components } from './openapi.generated'
import type {
  EntityTaxonomyDomainSchema,
  EntityTaxonomySchema,
  EntityTaxonomyTypeSchema,
} from './entities'
import type { ModuleSummaryListSchema, ModuleSummarySchema, ServerInfoSchema } from './server'
import type {
  DeniedIntentSchema,
  EnterpriseSyncStatusSchema,
  SyncAuthoritySchema,
  SyncHealthSchema,
  SyncStatusSchema,
} from './sync-status'
import type { StatsSchema } from './stats'
import type {
  AnalysisNotEmptyDetailsSchema,
  DenialDetailsSchema,
  EntityInUseDetailsSchema,
  ErrorBody,
  ErrorCode,
  ErrorEnvelope,
  FieldErrorSchema,
  InvalidParticipationDetailsSchema,
  LegacyInvalidDetailsSchema,
  MethodMismatchDetailsSchema,
  ProvenanceImmutableDetailsSchema,
  ValidationErrorDetailsSchema,
} from './errors'

/**
 * Type-level contract assertions: each hand-written effect Schema must produce exactly the type
 * the backend's OpenAPI document declares for that shape.
 *
 * These have to be *type*-level. The generated file is types only — it has no runtime
 * representation — so nothing here can be compared structurally at run time. `vitest --typecheck`
 * is what executes this file, and a mismatch is a compile error, not a failed expectation.
 *
 * Direction of ownership: the generated types are the oracle, the effect schemas are the subject.
 * The schemas stay hand-written because they carry decode semantics generated types do not; the
 * generation supplies the check, not the decoder.
 */

describe('error envelope', () => {
  it('decodes exactly the envelope the backend declares', () => {
    expectTypeOf<ErrorEnvelope>().toEqualTypeOf<Immutable<components['schemas']['ErrorEnvelope']>>()
    expectTypeOf<ErrorBody>().toEqualTypeOf<Immutable<components['schemas']['ErrorBody']>>()
  })

  it('covers exactly the codes the backend can return', () => {
    // A code added on the server without one here is a type error, which is the point: a client
    // branching on an incomplete union silently falls through to its default case.
    expectTypeOf<ErrorCode>().toEqualTypeOf<components['schemas']['ErrorBody']['code']>()
  })

  it('narrows each code’s details to the DTO that code carries', () => {
    expectTypeOf<SchemaType<typeof FieldErrorSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['FieldError']>
    >()
    expectTypeOf<SchemaType<typeof ValidationErrorDetailsSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ValidationErrorDetails']>
    >()
    expectTypeOf<SchemaType<typeof DenialDetailsSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DenialDetails']>
    >()
    expectTypeOf<SchemaType<typeof MethodMismatchDetailsSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['MethodMismatchDetails']>
    >()
    expectTypeOf<SchemaType<typeof AnalysisNotEmptyDetailsSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AnalysisNotEmptyDetails']>
    >()
    expectTypeOf<SchemaType<typeof EntityInUseDetailsSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['EntityInUseDetails']>
    >()
    expectTypeOf<SchemaType<typeof ProvenanceImmutableDetailsSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ProvenanceImmutableDetails']>
    >()
    expectTypeOf<SchemaType<typeof InvalidParticipationDetailsSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['InvalidParticipationDetails']>
    >()
    expectTypeOf<SchemaType<typeof LegacyInvalidDetailsSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['LegacyInvalidDetails']>
    >()
  })
})

describe('repository catalog', () => {
  it('decodes the counts the backend declares, with nothing optional it always sends', () => {
    // This decoder had two of the four totals optional and three of the six breakdowns missing
    // outright, so a client reading them found `undefined` where the route had sent a number. The
    // assertion is what stops that shape of gap from reopening.
    expectTypeOf<SchemaType<typeof StatsSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['RepositoryStatsResponse']>
    >()
  })

  it('decodes the module envelope and its rows exactly', () => {
    expectTypeOf<SchemaType<typeof ModuleSummaryListSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['LoadedModuleListResponse']>
    >()
    expectTypeOf<SchemaType<typeof ModuleSummarySchema>>().toEqualTypeOf<
      Immutable<components['schemas']['LoadedModuleResponse']>
    >()
  })
})

describe('platform surface', () => {
  it('decodes the server info the backend declares', () => {
    expectTypeOf<SchemaType<typeof ServerInfoSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ServerInfoResponse']>
    >()
  })

  it('decodes the sync status, its closed vocabularies included', () => {
    // These decoders predate the route having a schema, and they are *tighter* than a first-draft DTO
    // would be: `status`, `block_kind` and `blocked_reason` are closed literals the domain already
    // declares. Asserting every level is what makes the two definitions one — a literal added on the
    // server without one here is a compile error rather than a value no branch handles.
    expectTypeOf<SchemaType<typeof SyncStatusSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['SyncStatusResponse']>
    >()
    expectTypeOf<SchemaType<typeof EnterpriseSyncStatusSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['EnterpriseSyncStateResponse']>
    >()
    expectTypeOf<SchemaType<typeof SyncAuthoritySchema>>().toEqualTypeOf<
      Immutable<components['schemas']['SyncAuthorityResponse']>
    >()
    expectTypeOf<SchemaType<typeof SyncHealthSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['SyncHealthResponse']>
    >()
    expectTypeOf<SchemaType<typeof DeniedIntentSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DeniedIntentResponse']>
    >()
  })
})

describe('entity taxonomy', () => {
  it('decodes exactly the tree the backend declares', () => {
    // The decoder for this predates the route having a schema at all, so until now the two agreed by
    // coincidence. Asserting all three levels rather than only the envelope: a drift in the leaf is
    // what silently empties the tree, and the envelope would keep decoding.
    expectTypeOf<SchemaType<typeof EntityTaxonomySchema>>().toEqualTypeOf<
      Immutable<components['schemas']['EntityTaxonomyResponse']>
    >()
    expectTypeOf<SchemaType<typeof EntityTaxonomyDomainSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['TaxonomyDomainResponse']>
    >()
    expectTypeOf<SchemaType<typeof EntityTaxonomyTypeSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['TaxonomyTypeResponse']>
    >()
  })
})
