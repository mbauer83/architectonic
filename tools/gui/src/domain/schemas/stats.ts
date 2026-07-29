import { Schema } from 'effect'

export const StatsSchema = Schema.Struct({
  entities: Schema.Number,
  connections: Schema.Number,
  diagrams: Schema.Number,
  documents: Schema.optional(Schema.Number),
  entities_by_domain: Schema.Record({ key: Schema.String, value: Schema.Number }),
  connections_by_type: Schema.Record({ key: Schema.String, value: Schema.Number }),
  documents_by_type: Schema.optional(Schema.Record({ key: Schema.String, value: Schema.Number })),
})
export type Stats = typeof StatsSchema.Type
