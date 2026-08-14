import { Schema } from 'effect'

/**
 * What the governing meta-ontology declares about classifying things.
 *
 * Every field is decoded as it crosses — `id` and `source` as **opaque strings**, never as a union
 * over this meta-ontology's ids. A generated union would typecheck perfectly against `archimate-4-0`
 * and fail to compile the moment a second meta-ontology declared its own chain, which is the
 * failure the endpoint's own docstring records and the reason it is served as data at all.
 */
export const ClassificationLevelResponseSchema = Schema.Struct({
  id: Schema.String,
  label: Schema.String,
  source: Schema.String,
  required: Schema.Boolean,
  keys_relationships: Schema.Boolean,
  narrows_relationships: Schema.Boolean,
  carries_attributes: Schema.Boolean,
})

export const ClassificationLevelsResponseSchema = Schema.Struct({
  meta_ontology: Schema.String,
  entity: Schema.Array(ClassificationLevelResponseSchema),
  relation: Schema.Array(ClassificationLevelResponseSchema),
})

export type ClassificationLevelResponse = Schema.Schema.Type<typeof ClassificationLevelResponseSchema>
export type ClassificationLevelsResponse = Schema.Schema.Type<typeof ClassificationLevelsResponseSchema>
