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
  SyncChangedArtifactSchema,
  SyncChangesSchema,
  SyncHealthSchema,
  SyncStatusSchema,
} from './sync-status'
import type { StatsSchema } from './stats'
import type {
  PromotionMissingDependencySchema,
  PromotionPlanSchema,
  PromotionResultSchema,
  PromotionViewpointDependencySchema,
} from './promotion'
import type {
  ArtifactSearchHitSchema,
  ArtifactSearchResultSchema,
  ReferenceSearchHitSchema,
  ReferenceSearchResultSchema,
  SearchHitSchema,
  SearchResultSchema,
} from './search'
import type {
  SyncDiagramToModelResultSchema,
  VerificationIssueSchema,
  WriteResultSchema,
  WriteVerificationSchema,
} from './write-results'
import type { DocumentTypeSchema, DocumentTypesSchema, SectionSpecSchema } from './documents'
import type { GroupEntrySchema, GroupListSchema } from './groups'
import type { MatrixConfigSchema, MatrixConnTypeConfigSchema } from './diagrams'
import type {
  DiagramOwnEntityTypeUiConfigSchema,
  DiagramTypeSummarySchema,
  DiagramTypeUiConfigSchema,
  OntologyClassificationSchema,
  OntologyPairSchema,
} from './diagram-types'
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
  ClassificationNotPublishableDetailsSchema,
  ProvenanceImmutableDetailsSchema,
  UnknownGuidanceTopicDetailsSchema,
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
    expectTypeOf<SchemaType<typeof UnknownGuidanceTopicDetailsSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['UnknownGuidanceTopicDetails']>
    >()
    expectTypeOf<SchemaType<typeof ClassificationNotPublishableDetailsSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ClassificationNotPublishableDetails']>
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

  it('decodes the uncommitted changes the save dialog reads', () => {
    expectTypeOf<SchemaType<typeof SyncChangesSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['SyncChangesResponse']>
    >()
    expectTypeOf<SchemaType<typeof SyncChangedArtifactSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['SyncChangedArtifact']>
    >()
  })
})

describe('authoring catalogs', () => {
  it('decodes the document-type envelope, its rows and its section specs', () => {
    // Four of the row's fields were declared optional here while the route fills every one from the
    // schema with a default — so readers carried fallbacks for a response the server never sends.
    expectTypeOf<SchemaType<typeof DocumentTypesSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DocumentTypeListResponse']>
    >()
    expectTypeOf<SchemaType<typeof DocumentTypeSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DocumentTypeResponse']>
    >()
    expectTypeOf<SchemaType<typeof SectionSpecSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DocumentSectionSpec']>
    >()
  })
})

describe('groups and matrices', () => {
  it('decodes the group axes and their entries', () => {
    // An axis the `kind` filter left out is absent; an axis with no groups is an empty list. Both are
    // representable here, and the entry's ten fields are all required — eight were declared optional.
    expectTypeOf<SchemaType<typeof GroupListSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['GroupListResponse']>
    >()
    expectTypeOf<SchemaType<typeof GroupEntrySchema>>().toEqualTypeOf<
      Immutable<components['schemas']['GroupEntryResponse']>
    >()
  })

  it('decodes the matrix config, nulls present rather than absent', () => {
    expectTypeOf<SchemaType<typeof MatrixConfigSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['MatrixConfigResponse']>
    >()
    expectTypeOf<SchemaType<typeof MatrixConnTypeConfigSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['MatrixConnTypeConfig']>
    >()
  })
})

describe('promotion', () => {
  it('decodes the plan a person agrees to, and the result of carrying it out', () => {
    // Four of the plan's lists were optional here and two were absent outright —
    // `viewpoint_dependencies` and `missing_dependencies`, the two that can leave the enterprise
    // repository broken. `warnings` was missing from the result.
    expectTypeOf<SchemaType<typeof PromotionPlanSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['PromotionPlanResponse']>
    >()
    expectTypeOf<SchemaType<typeof PromotionResultSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['PromotionResultResponse']>
    >()
    expectTypeOf<SchemaType<typeof PromotionViewpointDependencySchema>>().toEqualTypeOf<
      Immutable<components['schemas']['PromotionViewpointDependency']>
    >()
    expectTypeOf<SchemaType<typeof PromotionMissingDependencySchema>>().toEqualTypeOf<
      Immutable<components['schemas']['PromotionMissingDependency']>
    >()
  })
})

describe('search', () => {
  it('decodes three searches as three searches', () => {
    // `ArtifactSearchHitSchema = SearchHitSchema` was the bug: the display search projects six fields
    // for a picker rather than serialising a record, and it can return `assurance-node`, which the
    // keyword search never does. The keyword hit also declared `last_updated` nowhere while the route
    // sent it on every hit — drift a decoder cannot report, because a field it does not know about
    // simply never appears.
    expectTypeOf<SchemaType<typeof SearchResultSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['KeywordSearchResponse']>
    >()
    expectTypeOf<SchemaType<typeof SearchHitSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['KeywordSearchHit']>
    >()
    expectTypeOf<SchemaType<typeof ArtifactSearchResultSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DisplaySearchResponse']>
    >()
    expectTypeOf<SchemaType<typeof ArtifactSearchHitSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DisplaySearchHit']>
    >()
    expectTypeOf<SchemaType<typeof ReferenceSearchResultSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ReferenceSearchResponse']>
    >()
    expectTypeOf<SchemaType<typeof ReferenceSearchHitSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ReferenceSearchHit']>
    >()
  })
})

describe('diagram types', () => {
  it('decodes the creatable types and one type authoring config', () => {
    // The construct schema described ten of eighteen fields and marked two of those ten optional
    // though the route always sends them. The eight it omitted govern authoring — `identity_scope`
    // decides whether editing one diagram can affect another — so a config decoded without them
    // looked complete. `permitted_connections` also used to arrive as `{"_rules": [...]}`: a private
    // field of a domain dataclass, published because `asdict` does not know what private means.
    expectTypeOf<SchemaType<typeof DiagramTypeSummarySchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DiagramTypeSummary']>
    >()
    expectTypeOf<SchemaType<typeof DiagramTypeUiConfigSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DiagramTypeUiConfigResponse']>
    >()
    expectTypeOf<SchemaType<typeof DiagramOwnEntityTypeUiConfigSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DiagramOwnEntityTypeResponse']>
    >()
  })
})

describe('ontology', () => {
  it('decodes each of the two reads the split produced', () => {
    // One address used to answer both shapes, selected by whether `target_type` was supplied. The client
    // had already split it into two calls with two decoders; the URLs now agree with that.
    expectTypeOf<SchemaType<typeof OntologyClassificationSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['OntologyClassificationResponse']>
    >()
    expectTypeOf<SchemaType<typeof OntologyPairSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['OntologyPairResponse']>
    >()
  })
})

describe('write results', () => {
  it('decodes the verification report every mutation returns', () => {
    // `verification` was `Schema.Unknown` against a server-side `dict[str, Any]`: neither side
    // described it, so every consumer re-derived the shape at the point of use. Asserting the issue as
    // well as the report — a drift in the issue is what would empty an authoring form's warning list
    // while the report around it still decoded.
    expectTypeOf<SchemaType<typeof WriteVerificationSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['WriteVerificationResponse']>
    >()
    expectTypeOf<SchemaType<typeof VerificationIssueSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['VerificationIssueResponse']>
    >()
  })

  it('decodes the mutation envelope that carries it', () => {
    expectTypeOf<SchemaType<typeof WriteResultSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['WriteResultResponse']>
    >()
  })

  it('decodes a diagram sync, whose body adds what reconciling pruned', () => {
    // `deleted_diagram` was on neither side: the handler did not copy it out of the result, so the
    // decoder had nothing to declare. It is the operation's own no-deletion guarantee.
    expectTypeOf<SchemaType<typeof SyncDiagramToModelResultSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['SyncDiagramToModelResponse']>
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
