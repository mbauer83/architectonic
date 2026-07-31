import { describe, expectTypeOf, it } from 'vitest'
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

type SchemaType<S> = S extends { readonly Type: infer T } ? T : never

/**
 * The oracle, with `readonly` applied throughout.
 *
 * Effect schemas decode arrays as `ReadonlyArray` on purpose — decoded data is not the caller's to
 * mutate — while `openapi-typescript` emits plain arrays because JSON Schema has no notion of
 * mutability. Making the schemas emit mutable arrays to satisfy a comparison would trade a real
 * property for a cosmetic one, so the modifier is normalised on the oracle side instead. `readonly`
 * is a modifier, not a shape: every structural difference still fails.
 */
type Immutable<T> = T extends (infer E)[]
  ? ReadonlyArray<Immutable<E>>
  : T extends ReadonlyArray<infer E>
    ? ReadonlyArray<Immutable<E>>
    : T extends object
      ? { readonly [K in keyof T]: Immutable<T[K]> }
      : T

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
