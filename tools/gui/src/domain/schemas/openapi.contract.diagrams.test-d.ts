import { describe, expectTypeOf, it } from 'vitest'
import type { Immutable, SchemaType } from './contractOracle'
import type { components } from './openapi.generated'
import type { EntityContextConnectionSchema } from './connections'
import type {
  DerivedEntitySchema,
  DiagramContextConnectionSchema,
  DiagramContextEntitySchema,
  DiagramEntityDiscoverySchema,
  DiagramPreviewResultSchema,
  HopSuggestionGroupSchema,
} from './diagrams'
import type { EntityDisplayInfoSchema, EntityDisplaySearchResultSchema } from './entities'

/**
 * Type-level contract assertions for the diagram palette — what a user can find to place on a
 * diagram, and what placing it would bring with it.
 *
 * These decoders were the better description of the payload than the server's own models were:
 * `display_alias` was declared nullable on the server against a record that stores it as a plain
 * string, and `direction` was a free string against a three-value bucket. Both are closed now, and
 * the assertions are what keep the two definitions one.
 */

describe('diagram palette', () => {
  it('decodes a page of placeable entities', () => {
    expectTypeOf<SchemaType<typeof EntityDisplaySearchResultSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['EntityDisplaySearchResponse']>
    >()
    expectTypeOf<SchemaType<typeof EntityDisplayInfoSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['EntityDisplayItemResponse']>
    >()
  })

  it('decodes the three-part discovery answer', () => {
    expectTypeOf<SchemaType<typeof DiagramEntityDiscoverySchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DiagramEntityDiscoveryResponse']>
    >()
    expectTypeOf<SchemaType<typeof EntityContextConnectionSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ContextConnection']>
    >()
  })

  it('decodes the rows a diagram context resolves', () => {
    // The envelope itself cannot be asserted: `read_diagram_extras` and `build_context_extras` are
    // diagram-type module hooks that contribute top-level keys, so it is open by design and the
    // schema promises nothing to compare against. Its rows are closed, and they are the part a
    // renderer reads field by field.
    expectTypeOf<SchemaType<typeof DiagramContextEntitySchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DiagramContextEntity']>
    >()
    expectTypeOf<SchemaType<typeof DiagramContextConnectionSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DiagramContextConnection']>
    >()
    expectTypeOf<SchemaType<typeof HopSuggestionGroupSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['HopSuggestionGroup']>
    >()
  })

  it('decodes a preview, the derived checklist included', () => {
    expectTypeOf<SchemaType<typeof DiagramPreviewResultSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DiagramPreviewResponse']>
    >()
    expectTypeOf<SchemaType<typeof DerivedEntitySchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DerivedViewEntityResponse']>
    >()
  })
})
