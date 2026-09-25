import { describe, expectTypeOf, it } from 'vitest'
import type { Immutable, SchemaType } from './contractOracle'
import type { components } from './openapi.generated'
import type { IconListSchema, IconSummarySchema, ShownIconsSchema } from './icons'

/** Type-level contract assertions for the icon library and the editor's preview of shown icons. */

describe('the icon library', () => {
  it('decodes a row as the list and the read both answer it', () => {
    expectTypeOf<SchemaType<typeof IconSummarySchema>>().toEqualTypeOf<
      Immutable<components['schemas']['IconSummary']>
    >()
  })

  it('decodes the list', () => {
    expectTypeOf<SchemaType<typeof IconListSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['IconListResponse']>
    >()
  })

  it('decodes which icon each instance shows', () => {
    expectTypeOf<SchemaType<typeof ShownIconsSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ShownIconsResponse']>
    >()
  })
})
