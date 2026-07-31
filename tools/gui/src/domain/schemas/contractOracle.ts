/**
 * Type helpers the contract assertions share.
 *
 * The generated OpenAPI types are the oracle and the hand-written effect schemas are the subject.
 * Comparing them needs two adjustments, and both belong here rather than in one test file so every
 * assertion makes the same ones.
 */

/** The type an effect Schema decodes to. */
export type SchemaType<S> = S extends { readonly Type: infer T } ? T : never

/**
 * The oracle, with `readonly` applied throughout.
 *
 * Effect schemas decode arrays as `ReadonlyArray` on purpose — decoded data is not the caller's to
 * mutate — while `openapi-typescript` emits plain arrays because JSON Schema has no notion of
 * mutability. Making the schemas emit mutable arrays to satisfy a comparison would trade a real
 * property for a cosmetic one, so the modifier is normalised on the oracle side instead. `readonly`
 * is a modifier, not a shape: every structural difference still fails, including the presence or
 * absence of `null` in a union and whether a key is optional.
 */
export type Immutable<T> = T extends (infer E)[]
  ? ReadonlyArray<Immutable<E>>
  : T extends ReadonlyArray<infer E>
    ? ReadonlyArray<Immutable<E>>
    : T extends object
      ? { readonly [K in keyof T]: Immutable<T[K]> }
      : T
