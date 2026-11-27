/**
 * A purpose line — who a view is for and what it answers — on the wire.
 *
 * One shape for a viewpoint definition and a diagram alike, mirroring the server's
 * `src/domain/purpose_lines.py`: each entry of `stakeholders` and `concerns` is prose, or a reference
 * `{ref}` to an element of the model.
 */
import { Schema } from 'effect'

/** An entry naming an element: a stakeholder for `stakeholders`, the element stating it for `concerns`. */
export const PurposeReferenceSchema = Schema.Struct({ ref: Schema.String })

/** One entry of a `stakeholders` or `concerns` list, as stated. */
export const PurposeEntrySchema = Schema.Union(Schema.String, PurposeReferenceSchema)
export type PurposeEntry = typeof PurposeEntrySchema.Type

/** One entry as a reader sees it: its words (a reference's element name), and the element where it is one. */
export const PurposeEntryShownSchema = Schema.Struct({
  text: Schema.String,
  ref: Schema.optional(Schema.String),
})
export type PurposeEntryShown = typeof PurposeEntryShownSchema.Type

/** The line a diagram shows: its own lists, each it does not state taken from its viewpoint. */
export const DiagramPurposeSchema = Schema.Struct({
  stakeholders: Schema.Array(PurposeEntryShownSchema),
  concerns: Schema.Array(PurposeEntryShownSchema),
  /** The viewpoint supplying at least one shown list; absent where both are the diagram's own. */
  inherited_from: Schema.optional(Schema.String),
})
export type DiagramPurpose = typeof DiagramPurposeSchema.Type
