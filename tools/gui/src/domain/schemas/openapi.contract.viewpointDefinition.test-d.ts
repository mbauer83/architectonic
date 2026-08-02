import { describe, expectTypeOf, it } from 'vitest'
import type { Immutable, SchemaType } from './contractOracle'
import type { components } from './openapi.generated'
import type { CriteriaCatalogSchema } from './viewpointCatalogs'
import type {
  ViewpointPersistResultSchema,
  ViewpointPinsSchema,
  ViewpointReferencerListSchema,
  ViewpointValidationIssueSchema,
} from './viewpoints'
import type {
  ConceptScopeSpecSchema,
  ForkLineageSpecSchema,
  ScopeSummarySchema,
  ViewpointDefinitionEnvelopeSchema,
  ViewpointDefinitionListSchema,
} from './viewpointDefinition'
import type {
  AttributeConditionNodeSchema,
  AttributeValueRefSchema,
  BindingValueRefSchema,
  ColumnSpecSchema,
  ConnectionCriteriaGroupNodeSchema,
  ConnectionSelectionSpecSchema,
  DerivedAttributeSpecSchema,
  DisplayOptionsSpecSchema,
  EntityCriteriaGroupNodeSchema,
  IncidentConnectionNodeSchema,
  NeighborInclusionSpecSchema,
  ParameterValueRefSchema,
  PresentationSpecWireSchema,
  QueryBindingSpecSchema,
  QueryParameterSpecSchema,
  RangeBandSpecSchema,
  StyleRuleSpecSchema,
  TracePatternSpecSchema,
  ViewpointQuerySpecSchema,
} from './viewpointLanguage'
import type { ViewpointSummarizeResultSchema } from './viewpoints'

/**
 * Type-level contract assertions for the viewpoint *authoring* surface — the catalogue entry, the
 * definition language it carries, and the pickers the editor is populated from.
 *
 * The language was `Schema.Unknown` on both `query` and `presentation` until the route had a
 * contract, so the one payload the editor round-trips whole was unchecked at both ends. Asserting
 * every level rather than only the envelope is what makes that useful: a drift in a leaf node is
 * what silently drops a criterion, and the envelope would keep decoding.
 */

describe('viewpoint catalogue entry', () => {
  it('decodes the envelope and its list', () => {
    expectTypeOf<SchemaType<typeof ViewpointDefinitionListSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ViewpointDefinitionListResponse']>
    >()
    expectTypeOf<SchemaType<typeof ViewpointDefinitionEnvelopeSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ViewpointDefinitionEnvelope']>
    >()
  })

  it('decodes the scope, its summary and the fork lineage', () => {
    expectTypeOf<SchemaType<typeof ConceptScopeSpecSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ConceptScopeSpec']>
    >()
    expectTypeOf<SchemaType<typeof ScopeSummarySchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ScopeSummaryResponse']>
    >()
    expectTypeOf<SchemaType<typeof ForkLineageSpecSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ForkLineageSpec']>
    >()
  })
})

describe('criteria tree', () => {
  it('decodes each node kind, recursion included', () => {
    expectTypeOf<SchemaType<typeof EntityCriteriaGroupNodeSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['EntityCriteriaGroupNode']>
    >()
    expectTypeOf<SchemaType<typeof ConnectionCriteriaGroupNodeSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ConnectionCriteriaGroupNode']>
    >()
    expectTypeOf<SchemaType<typeof AttributeConditionNodeSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AttributeConditionNode']>
    >()
    expectTypeOf<SchemaType<typeof IncidentConnectionNodeSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['IncidentConnectionNode']>
    >()
  })

  it('keeps a value reference distinguishable from a literal', () => {
    expectTypeOf<SchemaType<typeof ParameterValueRefSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ParameterValueRef']>
    >()
    expectTypeOf<SchemaType<typeof BindingValueRefSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['BindingValueRef']>
    >()
    expectTypeOf<SchemaType<typeof AttributeValueRefSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AttributeValueRef']>
    >()
  })

  it('decodes the two population terms built from the tree', () => {
    expectTypeOf<SchemaType<typeof NeighborInclusionSpecSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['NeighborInclusionSpec']>
    >()
    expectTypeOf<SchemaType<typeof ConnectionSelectionSpecSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ConnectionSelectionSpec']>
    >()
  })
})

describe('query and presentation', () => {
  it('decodes the query and everything it declares', () => {
    expectTypeOf<SchemaType<typeof ViewpointQuerySpecSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ViewpointQuerySpec']>
    >()
    expectTypeOf<SchemaType<typeof QueryBindingSpecSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['QueryBindingSpec']>
    >()
    expectTypeOf<SchemaType<typeof QueryParameterSpecSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['QueryParameterSpec']>
    >()
    expectTypeOf<SchemaType<typeof DerivedAttributeSpecSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DerivedAttributeSpec']>
    >()
    expectTypeOf<SchemaType<typeof TracePatternSpecSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['TracePatternSpec']>
    >()
  })

  it('decodes the presentation and its styling', () => {
    expectTypeOf<SchemaType<typeof PresentationSpecWireSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['PresentationSpecResponse']>
    >()
    expectTypeOf<SchemaType<typeof DisplayOptionsSpecSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DisplayOptionsSpec']>
    >()
    expectTypeOf<SchemaType<typeof ColumnSpecSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ColumnSpecResponse']>
    >()
    expectTypeOf<SchemaType<typeof StyleRuleSpecSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['StyleRuleSpec']>
    >()
    expectTypeOf<SchemaType<typeof RangeBandSpecSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['RangeBandSpec']>
    >()
  })
})

describe('authoring pickers', () => {
  it('decodes the criteria catalogue and the query summary', () => {
    expectTypeOf<SchemaType<typeof CriteriaCatalogSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['CriteriaCatalogResponse']>
    >()
    expectTypeOf<SchemaType<typeof ViewpointSummarizeResultSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ViewpointQuerySummaryResponse']>
    >()
  })
})

describe('persisting a definition', () => {
  /**
   * `version` carried `= None`, publishing as optional a key `PersistResult.as_answer` emits
   * unconditionally; and `ViewpointValidationIssueDto.expected`/`found` did the same while the DTO's
   * own docstring said both are always serialised. A default describes a field's *value*; it is the
   * absence of one that describes its presence.
   */
  it('decodes a persist outcome, with its issues and referencers', () => {
    expectTypeOf<SchemaType<typeof ViewpointPersistResultSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ViewpointPersistResponse']>
    >()
  })

  it('decodes one validation finding', () => {
    expectTypeOf<SchemaType<typeof ViewpointValidationIssueSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ViewpointValidationIssueDto']>
    >()
  })

  it('decodes the diagrams and matrices that pin a viewpoint', () => {
    expectTypeOf<SchemaType<typeof ViewpointReferencerListSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ViewpointReferencerListResponse']>
    >()
  })

  it('decodes the pin list', () => {
    expectTypeOf<SchemaType<typeof ViewpointPinsSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ViewpointPinsResponse']>
    >()
  })
})
