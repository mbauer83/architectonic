import { describe, expectTypeOf, it } from 'vitest'
import type { Immutable, SchemaType } from './contractOracle'
import type { components } from './openapi.generated'
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
