import { describe, expectTypeOf, it } from 'vitest'
import type { Immutable, SchemaType } from './contractOracle'
import type { components } from './openapi.generated'
import type {
  AggregateEdgeSchema,
  AggregateNodeSchema,
  AggregationSummarySchema,
  ConnectionItemSummarySchema,
  EntityItemSummarySchema,
  MatrixAxisIdsSchema,
  TargetPopulationSummarySchema,
  ViewpointExecutionResultSchema,
  WitnessStepSchema,
} from './viewpoints'
import type {
  AuthoritativePatternResultSchema,
  DiagnosticPatternResultSchema,
  MissingOutcomeObligationSchema,
  MissingRequirementObligationSchema,
  ShortcutObligationSchema,
  TerminalObligationSchema,
  TraceRowSchema,
  TraceTableSchema,
} from './viewpointTrace'

/**
 * Type-level contract assertions for the viewpoints surface, split from
 * `openapi.contract.test-d.ts` so both stay within the module-size policy.
 *
 * These decoders predate the routes having schemas, so until now the two agreed by
 * coincidence — and in two places they did not: `bound_parameters` accepted `unknown`
 * values where binding can only produce five, and a trace obligation was one struct with
 * four optional id fields where the server sends a four-arm discriminated union. Both are
 * the permissive direction, which is the one a green suite never notices.
 */

describe('viewpoint execution', () => {
  it('decodes the execution envelope exactly', () => {
    expectTypeOf<SchemaType<typeof ViewpointExecutionResultSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ViewpointExecutionResponse']>
    >()
  })

  it('decodes each selected item, its witness chain included', () => {
    expectTypeOf<SchemaType<typeof EntityItemSummarySchema>>().toEqualTypeOf<
      Immutable<components['schemas']['EntityItemSummaryResponse']>
    >()
    expectTypeOf<SchemaType<typeof ConnectionItemSummarySchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ConnectionItemSummaryResponse']>
    >()
    expectTypeOf<SchemaType<typeof WitnessStepSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['WitnessStepResponse']>
    >()
  })

  it('decodes the optional result projections the header reads', () => {
    expectTypeOf<SchemaType<typeof MatrixAxisIdsSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['MatrixAxisIdsResponse']>
    >()
    expectTypeOf<SchemaType<typeof TargetPopulationSummarySchema>>().toEqualTypeOf<
      Immutable<components['schemas']['TargetPopulationSummaryResponse']>
    >()
    expectTypeOf<SchemaType<typeof AggregationSummarySchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AggregationSummaryResponse']>
    >()
    expectTypeOf<SchemaType<typeof AggregateNodeSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AggregateNodeResponse']>
    >()
    expectTypeOf<SchemaType<typeof AggregateEdgeSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AggregateEdgeResponse']>
    >()
  })
})

describe('coverage trace', () => {
  it('decodes the table and its rows', () => {
    expectTypeOf<SchemaType<typeof TraceTableSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['TraceTableResponse']>
    >()
    expectTypeOf<SchemaType<typeof TraceRowSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['TraceRowResponse']>
    >()
  })

  it('keeps a diagnostic observation distinguishable from an authoritative verdict', () => {
    expectTypeOf<SchemaType<typeof AuthoritativePatternResultSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AuthoritativePatternResultResponse']>
    >()
    expectTypeOf<SchemaType<typeof DiagnosticPatternResultSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DiagnosticPatternResultResponse']>
    >()
  })

  it('narrows each obligation to the ids that arm actually carries', () => {
    expectTypeOf<SchemaType<typeof TerminalObligationSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['TerminalObligationResponse']>
    >()
    expectTypeOf<SchemaType<typeof ShortcutObligationSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ShortcutObligationResponse']>
    >()
    expectTypeOf<SchemaType<typeof MissingRequirementObligationSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['MissingRequirementObligationResponse']>
    >()
    expectTypeOf<SchemaType<typeof MissingOutcomeObligationSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['MissingOutcomeObligationResponse']>
    >()
  })
})
