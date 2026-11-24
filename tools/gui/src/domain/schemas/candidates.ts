import { Schema } from 'effect'
import { DiagramLayoutGeometrySchema } from './diagramLayoutGeometry'
import { WriteVerificationSchema } from './write-results'

/**
 * Candidate architectures and the stress-analysis reads over them (`/api/change-sets…`,
 * `/api/documents/{id}/progress|incidence|tables`).
 *
 * A candidate's record and an operation are served as open field maps: the server reads the recorded
 * form strictly, and the client states what it writes in `domain/candidates/candidateCanvas`.
 */
const FieldsSchema = Schema.Record({ key: Schema.String, value: Schema.Unknown })

export const CandidateSummarySchema = Schema.Struct({
  id: Schema.String,
  name: Schema.String,
  state: Schema.String,
  parent: Schema.NullOr(Schema.String),
})
export type CandidateSummary = typeof CandidateSummarySchema.Type

export const CandidateListSchema = Schema.Struct({ candidates: Schema.Array(CandidateSummarySchema) })

/** A candidate's record and the version an edit of it states as `based_on`. */
export const CandidateResponseSchema = Schema.Struct({ record: FieldsSchema, version: Schema.String })
export type CandidateResponse = typeof CandidateResponseSchema.Type

/** A started analysis: its document, and the naive architecture it was started with. */
export const AnalysisStartedSchema = Schema.Struct({
  document: Schema.String, naive_candidate: CandidateResponseSchema,
})
export type AnalysisStarted = typeof AnalysisStartedSchema.Type

const ConnectionKeySchema = Schema.Struct({
  source_entity: Schema.String,
  connection_type: Schema.String,
  target_entity: Schema.String,
})
export type ConnectionKey = typeof ConnectionKeySchema.Type

/** *artifact_id*: the id chosen for an entity the stack creates, which the view names by its reference. */
const ScopedEntitySchema = Schema.Struct({
  id: Schema.String, fields: FieldsSchema, artifact_id: Schema.optional(Schema.String),
})
const ScopedConnectionSchema = Schema.Struct({ ...ConnectionKeySchema.fields, fields: FieldsSchema })
export type ScopedEntity = typeof ScopedEntitySchema.Type
export type ScopedConnection = typeof ScopedConnectionSchema.Type

const ChangedFieldSchema = Schema.Struct({ before: Schema.Unknown, after: Schema.Unknown })

export const ChangeDifferenceSchema = Schema.Struct({
  kind: Schema.String,
  target: Schema.Union(Schema.String, ConnectionKeySchema),
  change: Schema.String,
  fields: Schema.Record({ key: Schema.String, value: ChangedFieldSchema }),
})
export type ChangeDifference = typeof ChangeDifferenceSchema.Type

export const OperationStandingSchema = Schema.Struct({
  operation: FieldsSchema,
  standing: Schema.String,
  reason: Schema.String,
})
export type OperationStanding = typeof OperationStandingSchema.Type

/** The candidate composed down its stack, against the chosen base, and the scope diagram's drawing. */
export const CandidateComparisonSchema = Schema.Struct({
  candidate: Schema.String,
  standing: Schema.Array(OperationStandingSchema),
  base: Schema.String,
  stack: Schema.Array(Schema.String),
  view: Schema.Struct({
    entities: Schema.Array(ScopedEntitySchema),
    connections: Schema.Array(ScopedConnectionSchema),
  }),
  diff: Schema.Array(ChangeDifferenceSchema),
  drawing: Schema.optional(DiagramLayoutGeometrySchema),
})
export type CandidateComparison = typeof CandidateComparisonSchema.Type

/** Structural overlaps between offered candidates: the same subject touched by more than one. */
export const IntegrationCheckSchema = Schema.Struct({
  candidates: Schema.Array(Schema.String),
  overlaps: Schema.Array(Schema.Struct({
    kind: Schema.String,
    subject: Schema.String,
    parties: Schema.Array(Schema.Struct({ set_id: Schema.String, operation: FieldsSchema })),
  })),
})
export type IntegrationCheck = typeof IntegrationCheckSchema.Type

export const AnalysisProgressSchema = Schema.Struct({
  document: Schema.String,
  naive_candidate: Schema.String,
  progress: Schema.Struct({
    unwalked: Schema.Array(Schema.String),
    without_end_state: Schema.Array(Schema.String),
    without_required_behaviour: Schema.Array(Schema.String),
    without_adaptation: Schema.Array(Schema.String),
    unexplained_hits: Schema.Array(Schema.String),
    incomplete_rows: Schema.Array(Schema.Struct({ table: Schema.String, row: Schema.String, column: Schema.String })),
  }),
  coverage: Schema.Struct({
    by_kind: Schema.Record({ key: Schema.String, value: Schema.Number }),
    unused_kinds: Schema.Array(Schema.String),
    single_stressor_end_states: Schema.Array(Schema.String),
    untouched: Schema.Array(Schema.Struct({ id: Schema.String, fan_in: Schema.Number, fan_out: Schema.Number })),
  }),
})
export type AnalysisProgress = typeof AnalysisProgressSchema.Type

export const AnalysisIncidenceSchema = Schema.Struct({
  document: Schema.String,
  naive_candidate: Schema.String,
  stressors: Schema.Array(FieldsSchema),
  end_states: Schema.Array(FieldsSchema),
  adaptations: Schema.Array(FieldsSchema),
  incidence: Schema.Array(FieldsSchema),
  coupling: Schema.Array(Schema.Struct({ left: Schema.String, right: Schema.String, count: Schema.Number })),
})
export type AnalysisIncidence = typeof AnalysisIncidenceSchema.Type

const CellScalarSchema = Schema.Union(Schema.String, Schema.Boolean, Schema.Number)
const CellValueSchema = Schema.Union(CellScalarSchema, Schema.Array(CellScalarSchema))
export type CellValue = typeof CellValueSchema.Type

export const DocumentTableRowSchema = Schema.Struct({
  row_id: Schema.String,
  values: Schema.Record({ key: Schema.String, value: CellValueSchema }),
  unreadable: Schema.Record({ key: Schema.String, value: Schema.String }),
})
export type DocumentTableRow = typeof DocumentTableRowSchema.Type

export const DocumentTablesSchema = Schema.Struct({
  tables: Schema.Array(Schema.Struct({
    name: Schema.String,
    section: Schema.String,
    found: Schema.Boolean,
    missing_columns: Schema.Array(Schema.String),
    undeclared_columns: Schema.Array(Schema.String),
    rows: Schema.Array(DocumentTableRowSchema),
  })),
})
export type DocumentTables = typeof DocumentTablesSchema.Type

export const DocumentTableWriteSchema = Schema.Struct({
  wrote: Schema.Boolean,
  path: Schema.String,
  artifact_id: Schema.String,
  content: Schema.NullOr(Schema.String),
  warnings: Schema.Array(Schema.String),
  verification: Schema.NullOr(WriteVerificationSchema),
  added_row_ids: Schema.Array(Schema.String),
})
export type DocumentTableWrite = typeof DocumentTableWriteSchema.Type
