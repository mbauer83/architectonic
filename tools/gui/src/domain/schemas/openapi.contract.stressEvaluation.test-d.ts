import { describe, expectTypeOf, it } from 'vitest'
import type { Immutable, SchemaType } from './contractOracle'
import type {
  AnalysisEvaluationSchema, CandidateResidualitySchema, HeldOutSchema, StressPerspectivesSchema,
} from './stressEvaluation'
import type { components } from './openapi.generated'

type Served<Name extends keyof components['schemas']> = Immutable<components['schemas'][Name]>

describe('the test set of a stress analysis', () => {
  it('decodes the test set, a hold-out, a candidate\'s residuality and the perspectives', () => {
    expectTypeOf<SchemaType<typeof AnalysisEvaluationSchema>>().toEqualTypeOf<Served<'AnalysisEvaluation'>>()
    expectTypeOf<SchemaType<typeof HeldOutSchema>>().toEqualTypeOf<Served<'HeldOut'>>()
    expectTypeOf<SchemaType<typeof CandidateResidualitySchema>>().toEqualTypeOf<Served<'CandidateResiduality'>>()
    expectTypeOf<SchemaType<typeof StressPerspectivesSchema>>().toEqualTypeOf<Served<'StressPerspectives'>>()
  })
})
