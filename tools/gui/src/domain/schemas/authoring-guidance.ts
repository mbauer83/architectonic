import { Schema } from 'effect'
import { EntityAttributeDescriptorSchema } from './entities'

export const PermittedConnectionsByPeerSchema = Schema.Struct({
  outgoing: Schema.Record({ key: Schema.String, value: Schema.Array(Schema.String) }),
  incoming: Schema.Record({ key: Schema.String, value: Schema.Array(Schema.String) }),
  symmetric: Schema.Record({ key: Schema.String, value: Schema.Array(Schema.String) }),
})

/**
 * The effective merged metadata schema a (connection-type, specialization) pair authors
 * against. Connections have no schema endpoint of their own — unlike entities, which fetch
 * theirs from /api/entity-schemata/{artifact_type} — so it rides along in the guidance payload. Absent when
 * the backend resolved no repository root.
 */
export const ConnectionMetadataSchemaSchema = Schema.Struct({
  /** Absent when no schema file declares one — this read omits what is not set. */
  schema: Schema.optional(Schema.Record({ key: Schema.String, value: Schema.Unknown })),
  properties: Schema.Array(Schema.String),
  required: Schema.Array(Schema.String),
  // Same descriptor shape the entity schema endpoint serves, so one typed input renders both.
  descriptors: Schema.Record({ key: Schema.String, value: EntityAttributeDescriptorSchema }),
  conflicts: Schema.Array(Schema.String),
  quarantined: Schema.Boolean,
})
export type ConnectionMetadataSchema = typeof ConnectionMetadataSchemaSchema.Type

export const SpecializationNotationSchema = Schema.Struct({
  icon: Schema.optional(Schema.String),
  color: Schema.optional(Schema.String),
})

export const SpecializationGuidanceSchema = Schema.Struct({
  slug: Schema.String,
  name: Schema.String,
  description: Schema.String,
  create_when: Schema.String,
  never_create_when: Schema.String,
  notation: Schema.optional(SpecializationNotationSchema),
  metadata_schema: Schema.optional(ConnectionMetadataSchemaSchema),
})
export type SpecializationGuidance = typeof SpecializationGuidanceSchema.Type

export const GuidanceContextLayerSchema = Schema.Struct({
  level: Schema.String,
  node: Schema.String,
  text: Schema.String,
})

export const EntityTypeGuidanceSchema = Schema.Struct({
  name: Schema.String,
  prefix: Schema.String,
  /** Present when the request selected types; a domain-filtered answer states the domain once
   * at the top instead of repeating it per row. */
  domain: Schema.optional(Schema.String),
  classes: Schema.Array(Schema.String),
  create_when: Schema.String,
  never_create_when: Schema.String,
  permitted_connections: PermittedConnectionsByPeerSchema,
  specializations: Schema.Array(SpecializationGuidanceSchema),
  // v2 layered guidance: composed ancestry context, broadest first. Absent when none.
  context: Schema.optional(Schema.Array(GuidanceContextLayerSchema)),
})
export type EntityTypeGuidance = typeof EntityTypeGuidanceSchema.Type

export const ConnectionTypeGuidanceSchema = Schema.Struct({
  name: Schema.String,
  // When to reach for this relationship, and when something else fits better — the same pair the
  // entity types carry, empty until an authoring-guidance import has run.
  create_when: Schema.String,
  never_create_when: Schema.String,
  specializations: Schema.Array(SpecializationGuidanceSchema),
  metadata_schema: Schema.optional(ConnectionMetadataSchemaSchema),
})
export type ConnectionTypeGuidance = typeof ConnectionTypeGuidanceSchema.Type

/** Which connection types are legal between one ordered pair. No `error` arm: an unknown target
 * is a 422 like every other bad input, where it used to arrive as a 200 carrying an error string
 * and a list of known types. */
export const PairGuidanceSchema = Schema.Struct({
  source: Schema.String,
  target: Schema.String,
  outgoing: Schema.Array(Schema.String),
  incoming: Schema.Array(Schema.String),
  symmetric: Schema.Array(Schema.String),
})
export type PairGuidance = typeof PairGuidanceSchema.Type

export const PermittedMappingSourceSchema = Schema.Struct({
  ontology: Schema.String,
  /** A source names either a type or a class, so the other is absent. */
  entity_type: Schema.optional(Schema.String),
  entity_class: Schema.optional(Schema.String),
  transparent: Schema.Boolean,
})

export const PermittedMappingsSchema = Schema.Struct({
  entity_types: Schema.Array(Schema.String),
  entity_classes: Schema.Array(Schema.String),
  sources: Schema.optional(Schema.Array(PermittedMappingSourceSchema)),
})

export const OwnEntityTypeGuidanceSchema = Schema.Struct({
  entity_type: Schema.String,
  label: Schema.String,
  /** The cardinality the kind requires on a diagram; `max` null means unbounded. */
  min: Schema.Number,
  /** Absent means unbounded. */
  max: Schema.optional(Schema.Number),
  classes: Schema.Array(Schema.String),
  create_when: Schema.String,
  never_create_when: Schema.String,
  permitted_mappings: Schema.optional(PermittedMappingsSchema),
  /** Field name -> what the kind does with it. Prose, because the answer is conditional on
   * whether the element maps to a model entity. */
  managed_fields: Schema.Record({ key: Schema.String, value: Schema.String }),
  domain_properties: Schema.optional(Schema.Record({ key: Schema.String, value: Schema.Unknown })),
})

export const BindingTargetSpecSchema = Schema.Struct({
  correspondence_kinds: Schema.Array(Schema.String),
  default_correspondence_kind: Schema.String,
  target_forms: Schema.Array(Schema.String),
  visual_roles: Schema.optional(Schema.Array(Schema.String)),
  /** Connection bindings only — an entity binding narrows by neither. */
  target_connection_types: Schema.optional(Schema.Array(Schema.String)),
  target_connection_classes: Schema.optional(Schema.Array(Schema.String)),
})

export const AllowedBindingsSchema = Schema.Struct({
  entity: Schema.Record({ key: Schema.String, value: BindingTargetSpecSchema }),
  connection: Schema.Record({ key: Schema.String, value: BindingTargetSpecSchema }),
})

export const DiagramTypeGuidanceSchema = Schema.Struct({
  name: Schema.String,
  when_to_use: Schema.String,
  when_not_to_use: Schema.String,
  accepted_domains: Schema.optional(Schema.Array(Schema.String)),
  diagram_entities_schema: Schema.optional(Schema.Record({ key: Schema.String, value: Schema.Unknown })),
  own_entity_types: Schema.optional(Schema.Array(OwnEntityTypeGuidanceSchema)),
  puml_notes: Schema.optional(Schema.Array(Schema.String)),
  allowed_bindings: Schema.optional(AllowedBindingsSchema),
  guidance_status: Schema.optional(Schema.Literal('empty')),
  guidance_hint: Schema.optional(Schema.String),
})
export type DiagramTypeGuidance = typeof DiagramTypeGuidanceSchema.Type

/** Four independent answers, each present only if it was asked for. No `error`/`unknown` arms:
 * a rejected request is a 422, so a 200 here always carries guidance. */
export const AuthoringGuidanceSchema = Schema.Struct({
  entity_types: Schema.optional(Schema.Array(EntityTypeGuidanceSchema)),
  total: Schema.optional(Schema.Number),
  domains: Schema.optional(Schema.Array(Schema.String)),
  connection_types: Schema.optional(Schema.Array(ConnectionTypeGuidanceSchema)),
  diagram_type_guidance: Schema.optional(DiagramTypeGuidanceSchema),
  pair_guidance: Schema.optional(PairGuidanceSchema),
  guidance_status: Schema.optional(Schema.Literal('empty')),
  guidance_hint: Schema.optional(Schema.String),
})
export type AuthoringGuidance = typeof AuthoringGuidanceSchema.Type
