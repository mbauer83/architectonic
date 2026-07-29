import { Schema } from 'effect'

/** One authored reference (entity/connection type, specialization slug, attribute path,
 * or entity-id anchor) that no longer resolves against the current model. Computed on
 * demand from (definition, model), never persisted — the same report is rendered as a
 * catalogue-list badge, per-reference editor notices, and execution warnings. */
export const BrokenReferenceSchema = Schema.Struct({
  kind: Schema.Literal('entity-type', 'connection-type', 'specialization', 'attribute-path', 'entity-id'),
  reference: Schema.String,
  locus: Schema.String,
  severity: Schema.Literal('ontology', 'entity-id'),
})
export type BrokenReference = typeof BrokenReferenceSchema.Type
