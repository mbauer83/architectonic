import { describe, expectTypeOf, it } from 'vitest'
import type { Immutable, SchemaType } from './contractOracle'
import type {
  DiagramLayoutGeometrySchema, DiagramLayoutPatchResultSchema, DrawingNodeSchema, ShapeDrawingsSchema,
} from './diagramLayoutGeometry'
import type { components } from './openapi.generated'

describe('arranging a diagram', () => {
  it('decodes the picture a diagram is arranged on', () => {
    expectTypeOf<SchemaType<typeof DiagramLayoutGeometrySchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DiagramLayoutGeometryResponse']>
    >()
    expectTypeOf<SchemaType<typeof DrawingNodeSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DrawingNodeContract']>
    >()
  })

  it('decodes resized shapes drawn anew, and what a layout patch did', () => {
    expectTypeOf<SchemaType<typeof ShapeDrawingsSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ShapeDrawingsResponse']>
    >()
    expectTypeOf<SchemaType<typeof DiagramLayoutPatchResultSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DiagramLayoutPatchResponse']>
    >()
  })
})
