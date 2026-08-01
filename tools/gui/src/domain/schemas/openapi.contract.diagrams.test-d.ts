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
import type {
  AllowedBindingsSchema,
  AuthoringGuidanceSchema,
  BindingTargetSpecSchema,
  ConnectionMetadataSchemaSchema,
  ConnectionTypeGuidanceSchema,
  DiagramTypeGuidanceSchema,
  EntityTypeGuidanceSchema,
  GuidanceContextLayerSchema,
  OwnEntityTypeGuidanceSchema,
  PairGuidanceSchema,
  PermittedConnectionsByPeerSchema,
  PermittedMappingSourceSchema,
  PermittedMappingsSchema,
  SpecializationGuidanceSchema,
  SpecializationNotationSchema,
} from './authoring-guidance'

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

describe('authoring guidance', () => {
  it('decodes the four answers and the type rows they carry', () => {
    expectTypeOf<SchemaType<typeof AuthoringGuidanceSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AuthoringGuidanceResponse']>
    >()
    expectTypeOf<SchemaType<typeof EntityTypeGuidanceSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['EntityTypeGuidance']>
    >()
    expectTypeOf<SchemaType<typeof ConnectionTypeGuidanceSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['ConnectionTypeGuidance']>
    >()
    expectTypeOf<SchemaType<typeof PermittedConnectionsByPeerSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['PermittedConnectionsByPeer']>
    >()
    expectTypeOf<SchemaType<typeof GuidanceContextLayerSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['GuidanceContextLayer']>
    >()
  })

  it('decodes a pair answer with no error arm', () => {
    // It had one: an unknown target arrived as a 200 whose `pair_guidance` carried `error` and
    // `known_types`. Only the top-level error was translated, so this one reached clients.
    expectTypeOf<SchemaType<typeof PairGuidanceSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['PairGuidance']>
    >()
  })

  it('decodes a specialization and the schema it authors against', () => {
    expectTypeOf<SchemaType<typeof SpecializationGuidanceSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['SpecializationGuidance']>
    >()
    expectTypeOf<SchemaType<typeof SpecializationNotationSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['SpecializationNotation']>
    >()
    expectTypeOf<SchemaType<typeof ConnectionMetadataSchemaSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['MetadataSchemaBlock']>
    >()
  })

  it('decodes a diagram kind’s own guidance, bindings included', () => {
    expectTypeOf<SchemaType<typeof DiagramTypeGuidanceSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DiagramTypeGuidance']>
    >()
    expectTypeOf<SchemaType<typeof OwnEntityTypeGuidanceSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['OwnEntityTypeGuidance']>
    >()
    expectTypeOf<SchemaType<typeof PermittedMappingsSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['PermittedMappings']>
    >()
    expectTypeOf<SchemaType<typeof PermittedMappingSourceSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['PermittedMappingSource']>
    >()
    expectTypeOf<SchemaType<typeof AllowedBindingsSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AllowedBindings']>
    >()
    expectTypeOf<SchemaType<typeof BindingTargetSpecSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['BindingTargetSpec']>
    >()
  })
})
