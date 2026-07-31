import { Schema } from 'effect'

/**
 * Repository-wide counts, as `GET /api/stats` serves them.
 *
 * Every field is required and all six breakdowns are present. This decoder used to declare `documents`
 * and `documents_by_type` optional and to omit the three by-group maps entirely — the route always sent
 * all of them, so the optionality described nothing and the missing three were simply dropped on decode.
 * The route now publishes a closed schema and `openapi.contract.test-d.ts` holds the two together.
 */
export const StatsSchema = Schema.Struct({
  entities: Schema.Number,
  connections: Schema.Number,
  diagrams: Schema.Number,
  documents: Schema.Number,
  entities_by_domain: Schema.Record({ key: Schema.String, value: Schema.Number }),
  connections_by_type: Schema.Record({ key: Schema.String, value: Schema.Number }),
  documents_by_type: Schema.Record({ key: Schema.String, value: Schema.Number }),
  entities_by_group: Schema.Record({ key: Schema.String, value: Schema.Number }),
  diagrams_by_group: Schema.Record({ key: Schema.String, value: Schema.Number }),
  documents_by_group: Schema.Record({ key: Schema.String, value: Schema.Number }),
})
export type Stats = typeof StatsSchema.Type
