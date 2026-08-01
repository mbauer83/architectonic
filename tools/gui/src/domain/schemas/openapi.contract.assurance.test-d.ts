import { describe, expectTypeOf, it } from 'vitest'
import type { Immutable, SchemaType } from './contractOracle'
import type { components } from './openapi.generated'
import type {
  AnalysisMethod,
  AnalysisStatus,
  AssuranceAnalysisDetailSchema,
  AssuranceAnalysisListSchema,
  AssuranceAnalysisRecordSchema,
  AssuranceAnalysisSummarySchema,
  AssuranceGroupListSchema,
  AssuranceGroupRecordSchema,
  AssuranceParticipatingNodesSchema,
  AssuranceAnalysisCompletenessSchema,
  AssuranceCompletenessCheckSchema,
  AssuranceCompletenessReportSchema,
  AssuranceEdgeCatalogSchema,
  AssuranceEdgeTypePairSchema,
  AssuranceSearchHitSchema,
  AssuranceSearchSchema,
} from './assurance-analyses'
import type {
  AssuranceBaselineListSchema,
  AssuranceBaselineSchema,
  AssuranceNeighborhoodEdgeSchema,
  AssuranceNeighborhoodNodeSchema,
  AssuranceNeighborhoodSchema,
  AssuranceNodeListSchema,
  AssuranceNodeSchema,
} from './assurance'
import type {
  ActionPriority,
  AssessmentState,
  FmeaCellSchema,
  FmeaMatrixRowSchema,
  FmeaMatrixSchema,
} from './assurance-fmea'
import type {
  AiBomCandidateSchema,
  AiBomComponentCoverageSchema,
  AiBomCoverageSchema,
  AiBomRolesSchema,
  AiBomScanSchema,
} from './assurance-aibom'

/**
 * The assurance half of the type-level contract assertions.
 *
 * Split out of `openapi.contract.test-d.ts` when that file crossed the 350-line limit. The seam is the
 * one the contracts themselves use: the assurance surface reads from the confidential store, and its
 * DTOs live in their own modules for the same reason.
 *
 * Same rules as the other half. The generated types are the oracle and the effect schemas are the
 * subject; the assertions have to be type-level, because the generated file has no runtime
 * representation to compare against.
 */

describe('assurance analyses', () => {
  it('decodes the collection, the detail read and the record they share', () => {
    expectTypeOf<SchemaType<typeof AssuranceAnalysisListSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AssuranceAnalysisListResponse']>
    >()
    expectTypeOf<SchemaType<typeof AssuranceAnalysisDetailSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AssuranceAnalysisDetailResponse']>
    >()
    expectTypeOf<SchemaType<typeof AssuranceAnalysisRecordSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AssuranceAnalysisRecord']>
    >()
  })

  it('decodes the filing groups and the participations an analysis holds', () => {
    expectTypeOf<SchemaType<typeof AssuranceGroupListSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AssuranceGroupListResponse']>
    >()
    expectTypeOf<SchemaType<typeof AssuranceGroupRecordSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AssuranceGroupRecord']>
    >()
    expectTypeOf<SchemaType<typeof AssuranceParticipatingNodesSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AssuranceParticipatingNodesResponse']>
    >()
  })

  it('decodes a store-wide search and the analysis summary its hits carry', () => {
    expectTypeOf<SchemaType<typeof AssuranceSearchSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AssuranceSearchResponse']>
    >()
    expectTypeOf<SchemaType<typeof AssuranceSearchHitSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AssuranceSearchHit']>
    >()
    expectTypeOf<SchemaType<typeof AssuranceAnalysisSummarySchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AssuranceAnalysisSummary']>
    >()
  })

  it('decodes the node record every backend now returns', () => {
    // Wrong in both directions before: it required `created_by`, which only SQLCipher sends, and
    // omitted `failure_type` and `mode`, which every store writes. Only this assertion catches the
    // second kind — a decoder missing a field the server sends still decodes.
    expectTypeOf<SchemaType<typeof AssuranceNodeSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AssuranceNodeRecord']>
    >()
    expectTypeOf<SchemaType<typeof AssuranceNodeListSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AssuranceNodeListResponse']>
    >()
  })

  it('decodes the sealed baselines', () => {
    // Both halves of the seal. A fixture in the HTTP tests named `sealed_at`, which is not a field of
    // anything the archive returns, and another asserted `sealed: true` — an unverifiable
    // acknowledgement where the real reply carries the log position it sealed.
    expectTypeOf<SchemaType<typeof AssuranceBaselineListSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AssuranceBaselineListResponse']>
    >()
    expectTypeOf<SchemaType<typeof AssuranceBaselineSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AssuranceBaselineRecord']>
    >()
  })

  it('decodes a neighbourhood traversal, its budget included', () => {
    // The view's own types carried five of the node's nineteen fields, declared `edge_id` optional for
    // a route that always sends it, and had no `max_hops` at all — so a hop count clamped by the
    // deployment looked as though the request had been honoured.
    expectTypeOf<SchemaType<typeof AssuranceNeighborhoodSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AssuranceNeighborhoodResponse']>
    >()
    expectTypeOf<SchemaType<typeof AssuranceNeighborhoodNodeSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AssuranceNeighborhoodNode']>
    >()
    expectTypeOf<SchemaType<typeof AssuranceNeighborhoodEdgeSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AssuranceNeighborhoodEdge']>
    >()
  })

  it('decodes the FMEA matrix, its rows and its cells', () => {
    expectTypeOf<SchemaType<typeof FmeaMatrixSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['FmeaMatrixResponse']>
    >()
    expectTypeOf<SchemaType<typeof FmeaMatrixRowSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['FmeaMatrixRow']>
    >()
    expectTypeOf<SchemaType<typeof FmeaCellSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['FmeaCellView']>
    >()
  })

  it('covers exactly the action-priority bands and assessment states', () => {
    // `indeterminate` is a band, not an absence. A client whose union omitted it would fall through
    // to its default branch and paint an unrated cell as a rated one.
    expectTypeOf<ActionPriority>().toEqualTypeOf<
      components['schemas']['FmeaCellView']['action_priority']
    >()
    expectTypeOf<AssessmentState>().toEqualTypeOf<components['schemas']['FmeaCellView']['state']>()
  })

  it('decodes the AI-BOM scan, roles and coverage', () => {
    // `bom` itself is not asserted: it is a CycloneDX document, declared open on both sides, and the
    // assertion would compare two deliberate `unknown`s.
    expectTypeOf<SchemaType<typeof AiBomScanSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AiBomScanResponse']>
    >()
    expectTypeOf<SchemaType<typeof AiBomCandidateSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AiBomCandidate']>
    >()
    expectTypeOf<SchemaType<typeof AiBomRolesSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AiBomRolesResponse']>
    >()
    expectTypeOf<SchemaType<typeof AiBomCoverageSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AiBomCoverageResponse']>
    >()
    expectTypeOf<SchemaType<typeof AiBomComponentCoverageSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AiBomComponentCoverage']>
    >()
  })

  it('decodes the edge catalog, grouped per node-type pair as the picker asks it', () => {
    expectTypeOf<SchemaType<typeof AssuranceEdgeCatalogSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AssuranceEdgeCatalogResponse']>
    >()
    expectTypeOf<SchemaType<typeof AssuranceEdgeTypePairSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AssuranceEdgeTypePair']>
    >()
  })

  it('decodes the completeness report the analysis own method decides', () => {
    // Four endpoints used to answer this, each taking the analysis as an *optional* query parameter —
    // so a CAST report about an STPA analysis came back empty and read like a clean bill of health.
    expectTypeOf<SchemaType<typeof AssuranceAnalysisCompletenessSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AssuranceAnalysisCompletenessResponse']>
    >()
    expectTypeOf<SchemaType<typeof AssuranceCompletenessReportSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AssuranceCompletenessReport']>
    >()
    expectTypeOf<SchemaType<typeof AssuranceCompletenessCheckSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AssuranceCompletenessCheck']>
    >()
  })

  it('covers exactly the methods and statuses the backend declares', () => {
    // The picker's own `ANALYSIS_METHODS` list existed with a comment saying a test holds it equal to
    // a tuple in a Python file. The document declares the vocabulary now, so the check is a type
    // error rather than a string comparison — and FMEA missing from that list is what once made every
    // FMEA analysis unreachable from the matrix page.
    expectTypeOf<AnalysisMethod>().toEqualTypeOf<
      components['schemas']['AssuranceAnalysisRecord']['method']
    >()
    expectTypeOf<AnalysisStatus>().toEqualTypeOf<
      components['schemas']['AssuranceAnalysisRecord']['status']
    >()
  })
})
