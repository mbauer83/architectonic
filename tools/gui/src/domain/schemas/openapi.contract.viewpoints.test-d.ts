import { describe, expectTypeOf, it } from 'vitest'
import type { Immutable, SchemaType } from './contractOracle'
import type { components } from './openapi.generated'
import type {
  AggregateEdgeSchema,
  AggregateNodeSchema,
  AggregationSummarySchema,
  AppliedDiagramViewpointSchema,
  ConnectionItemSummarySchema,
  DiagramViewpointProjectionSchema,
  EntityItemSummarySchema,
  MatrixAxisIdsSchema,
  NoDiagramViewpointSchema,
  ProjectedOccurrenceSchema,
  ScaleLegendDataSchema,
  ScaleStyleValueSchema,
  StyleRuleOutcomeSchema,
  SignalBannerSchema,
  SignalBasisSnapshotSchema,
  TargetPopulationSummarySchema,
  ViewpointDiagramResultSchema,
  ViewpointExecutionResultSchema,
  ViewpointProjectionSchema,
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

describe('ad-hoc diagram render', () => {
  it('decodes the render and its classification banner', () => {
    // `entity_aliases` and `signal_banner` were both optional here against a route that keys them
    // on every response — so click-to-select carried a fallback for a map it always receives.
    expectTypeOf<SchemaType<typeof ViewpointDiagramResultSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ViewpointDiagramRenderResponse']>
    >()
    expectTypeOf<SchemaType<typeof SignalBannerSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['SignalBannerResponse']>
    >()
    expectTypeOf<SchemaType<typeof SignalBasisSnapshotSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['SignalBasisSnapshotResponse']>
    >()
  })
})

describe('viewpoint projection', () => {
  it('decodes the repository projection, whose every field is present', () => {
    // `index_generation` was missing from the decoder outright, so the one field that lets a
    // caller prove a result and its styling came from the same snapshot was stripped on decode.
    expectTypeOf<SchemaType<typeof ViewpointProjectionSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ViewpointProjectionResponse']>
    >()
  })

  it('decodes a diagram projection as the two answers it actually is', () => {
    expectTypeOf<SchemaType<typeof DiagramViewpointProjectionSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DiagramViewpointProjectionResponse']>
    >()
    expectTypeOf<SchemaType<typeof NoDiagramViewpointSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['NoDiagramViewpointResponse']>
    >()
    expectTypeOf<SchemaType<typeof AppliedDiagramViewpointSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AppliedDiagramViewpointResponse']>
    >()
  })

  it('decodes a projected occurrence whole, connection legs included', () => {
    // Eight of its fourteen fields were undeclared, and an effect struct strips what it does not
    // declare — a derived connection arrived with its certainty, hops and witness ids gone.
    expectTypeOf<SchemaType<typeof ProjectedOccurrenceSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ProjectedOccurrenceResponse']>
    >()
    expectTypeOf<SchemaType<typeof ScaleStyleValueSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ScaleStyleValueResponse']>
    >()
    expectTypeOf<SchemaType<typeof ScaleLegendDataSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ScaleLegendResponse']>
    >()
    expectTypeOf<SchemaType<typeof StyleRuleOutcomeSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['StyleRuleOutcomeResponse']>
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
