import { describe, expectTypeOf, it } from 'vitest'
import type { Immutable, SchemaType } from './contractOracle'
import type {
  AllocatedIdentifierSchema,
  DatatypeClassifierInfoSchema,
  DatatypeTypeCatalogSchema,
  DatatypeTypeUsageSchema,
  DatatypeTypeUsagesSchema,
  DiagramRefListSchema,
} from './diagram-types'
import type { components } from './openapi.generated'
import type { EntityContextConnectionSchema } from './connections'
import type { DiagramDetailSchema } from './diagrams'
import type {
  AttributeOfferSchema,
  DerivedEntitySchema,
  DiagramAttributePanelSchema,
  DiagramContextConnectionSchema,
  DiagramContextEntitySchema,
  DiagramContextSchema,
  DiagramEntityDiscoverySchema,
  DiagramPreviewResultSchema,
  HopSuggestionGroupSchema,
  MatrixPreviewResultSchema,
  TypeOfferSchema,
} from './diagrams'
import type {
  EntityAttributeDescriptorSchema,
  EntityAttributeItemDescriptorSchema,
  EntityDisplayInfoSchema,
  EntityDisplaySearchResultSchema,
  EntitySchemaInfoSchema,
} from './entities'
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

  it('decodes a diagram read and its context, envelopes included', () => {
    // Both envelopes were open until the module hooks were namespaced under `type_extras`: a hook
    // free to add a key beside the declared fields made the whole response an object promising
    // nothing, and neither could be asserted at all.
    expectTypeOf<SchemaType<typeof DiagramDetailSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DiagramDetailResponse']>
    >()
    expectTypeOf<SchemaType<typeof DiagramContextSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DiagramContextResponse']>
    >()
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

  it('decodes a matrix dry run', () => {
    // Recorded as a client-side composite "the server never sends whole", which was simply untrue:
    // `POST /api/matrices/preview` sends exactly this. The route meanwhile declared the six-key
    // mutation envelope and returned `{markdown}`, so it answered 500 to every caller — and the
    // wrong exemption here is what kept anything from noticing.
    expectTypeOf<SchemaType<typeof MatrixPreviewResultSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['MatrixPreviewResponse']>
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

  it('decodes the attribute schema both surfaces serve from one producer', () => {
    // `attribute_descriptors` feeds the entity schema route and the guidance payload, so the
    // descriptor is one shape; it was `dict[str, Any]` on the entity side, which is how the two
    // came to be described differently at the client.
    expectTypeOf<SchemaType<typeof EntitySchemaInfoSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['EntitySchemaResponse']>
    >()
    expectTypeOf<SchemaType<typeof EntityAttributeDescriptorSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AttributeDescriptor']>
    >()
    expectTypeOf<SchemaType<typeof EntityAttributeItemDescriptorSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AttributeItemDescriptor']>
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

describe('identifier allocation', () => {
  it('decodes an allocated diagram-entity identifier', () => {
    expectTypeOf<SchemaType<typeof AllocatedIdentifierSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AllocatedIdentifierResponse']>
    >()
  })
})

describe('the datatype classifier catalogue', () => {
  it('decodes a page of classifier types, and one classifier', () => {
    expectTypeOf<SchemaType<typeof DatatypeTypeCatalogSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DatatypeTypeListResponse']>
    >()
    expectTypeOf<SchemaType<typeof DatatypeClassifierInfoSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DatatypeClassifierInfo']>
    >()
  })

  it('decodes where a classifier type is used', () => {
    expectTypeOf<SchemaType<typeof DatatypeTypeUsagesSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DatatypeTypeUsageResponse']>
    >()
    expectTypeOf<SchemaType<typeof DatatypeTypeUsageSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DatatypeTypeUsage']>
    >()
  })
})

describe('diagram references', () => {
  // The envelope existed only as an anonymous `Schema.Struct` inside `getDiagramRefs`, so nothing
  // could hold it against the document while the bare array beside it looked like the response.
  it('decodes which diagrams draw a given pair', () => {
    expectTypeOf<SchemaType<typeof DiagramRefListSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DiagramReferenceListResponse']>
    >()
  })
})

describe("what a diagram's entities can be coloured by and print", () => {
  // Held against the document at every level rather than only the envelope: the two inner shapes
  // carry the decisions a reader acts on — which colouring an attribute admits, and how many drawn
  // entities have a value — and an envelope assertion alone would pass while either drifted.
  it('decodes the panel, its type rows and its attribute rows', () => {
    expectTypeOf<SchemaType<typeof DiagramAttributePanelSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['DiagramAttributePanelResponse']>
    >()
    expectTypeOf<SchemaType<typeof TypeOfferSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['TypeOfferResponse']>
    >()
    expectTypeOf<SchemaType<typeof AttributeOfferSchema>>().toEqualTypeOf<
      Immutable<components['schemas']['AttributeOfferResponse']>
    >()
  })
})
