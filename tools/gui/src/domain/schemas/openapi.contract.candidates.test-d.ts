import { describe, expectTypeOf, it } from 'vitest'
import type { Immutable, SchemaType } from './contractOracle'
import type {
  AnalysisIncidenceSchema, AnalysisProgressSchema, AnalysisStartedSchema, CandidateApplicationSchema,
  CandidateDiagramSavedSchema, CandidateIntegrationSchema, CandidateMoveSchema, CandidateTargetStateApplicationSchema,
  CandidateWithdrawalSchema,
  CandidateComparisonSchema,
  CandidateListSchema,
  CandidateResponseSchema, DocumentTablesSchema, DocumentTableWriteSchema, IntegrationCheckSchema,
} from './candidates'
import type { PictureContextSchema, PictureStartSchema } from './diagrams'
import type { components } from './openapi.generated'

type Served<Name extends keyof components['schemas']> = Immutable<components['schemas'][Name]>

describe('candidate architectures', () => {
  it('decodes the list, a record with its version, and a comparison against a base', () => {
    expectTypeOf<SchemaType<typeof CandidateListSchema>>().toEqualTypeOf<Served<'CandidateList'>>()
    expectTypeOf<SchemaType<typeof CandidateResponseSchema>>().toEqualTypeOf<Served<'CandidateResponse'>>()
    expectTypeOf<SchemaType<typeof CandidateComparisonSchema>>().toEqualTypeOf<Served<'CandidateComparison'>>()
    expectTypeOf<SchemaType<typeof IntegrationCheckSchema>>().toEqualTypeOf<Served<'IntegrationCheck'>>()
    expectTypeOf<SchemaType<typeof AnalysisStartedSchema>>().toEqualTypeOf<Served<'AnalysisStarted'>>()
    expectTypeOf<SchemaType<typeof CandidateApplicationSchema>>().toEqualTypeOf<Served<'CandidateApplication'>>()
    expectTypeOf<SchemaType<typeof CandidateDiagramSavedSchema>>().toEqualTypeOf<Served<'CandidateDiagramSaved'>>()
    expectTypeOf<SchemaType<typeof CandidateIntegrationSchema>>().toEqualTypeOf<Served<'CandidateIntegration'>>()
    expectTypeOf<SchemaType<typeof CandidateTargetStateApplicationSchema>>()
      .toEqualTypeOf<Served<'CandidateTargetStateApplication'>>()
    expectTypeOf<SchemaType<typeof CandidateMoveSchema>>().toEqualTypeOf<Served<'CandidateMove'>>()
    expectTypeOf<SchemaType<typeof CandidateWithdrawalSchema>>().toEqualTypeOf<Served<'CandidateWithdrawal'>>()
  })

  it('decodes the picture a candidate is sketched on, as a diagram editor reads a diagram', () => {
    expectTypeOf<SchemaType<typeof PictureStartSchema>>().toEqualTypeOf<Served<'PictureStartResponse'>>()
    expectTypeOf<SchemaType<typeof PictureContextSchema>>().toEqualTypeOf<Served<'CandidatePictureContext'>>()
  })
})

describe('the stress-analysis reads', () => {
  it('decodes progress, incidence, and the typed tables with their row edit', () => {
    expectTypeOf<SchemaType<typeof AnalysisProgressSchema>>().toEqualTypeOf<Served<'AnalysisProgress'>>()
    expectTypeOf<SchemaType<typeof AnalysisIncidenceSchema>>().toEqualTypeOf<Served<'AnalysisIncidence'>>()
    expectTypeOf<SchemaType<typeof DocumentTablesSchema>>().toEqualTypeOf<Served<'DocumentTablesResponse'>>()
    expectTypeOf<SchemaType<typeof DocumentTableWriteSchema>>().toEqualTypeOf<Served<'DocumentTableWriteResponse'>>()
  })
})
