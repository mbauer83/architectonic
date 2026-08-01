import { describe, expectTypeOf, it } from 'vitest'
import type { Immutable, SchemaType } from './contractOracle'
import type { components } from './openapi.generated'
import type { EntityContextConnectionSchema } from './connections'
import type { DiagramEntityDiscoverySchema } from './diagrams'
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
})
