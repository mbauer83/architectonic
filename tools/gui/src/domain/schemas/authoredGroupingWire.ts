/** The labelled boxes a diagram draws that the model does not hold, as the diagram read and its saves
 * carry them. Lifted from `diagrams.ts`, which re-exports both names. */
import { Schema } from 'effect'

/**
 * One labelled box a diagram draws that the model does not hold.
 *
 * Recursive, because boxes nest. `entity-ids` keeps its frontmatter spelling on the wire, so what is
 * read is what is written back, and a member may name an entity or a single occurrence of one.
 */
export interface AuthoredGroupingWire {
  /** The box's own stable identity, which a layout addresses it by. Sent back as read; a box
   * without one is new, and the backend gives it one. */
  readonly id?: string
  readonly label: string
  /** Empty on a box whose members a rule selects. */
  readonly 'entity-ids': readonly string[]
  /** Instead of listed members: one of `domain` or `type` to the name it selects. Not edited here,
   * and carried through every save untouched. */
  readonly rule?: Readonly<Record<string, string>>
  readonly groups?: readonly AuthoredGroupingWire[]
  /** An override the backend still honours; the look is otherwise derived from the members. */
  readonly stereotype?: string
}

export const AuthoredGroupingSchema: Schema.Schema<AuthoredGroupingWire> = Schema.Struct({
  id: Schema.optional(Schema.String),
  label: Schema.String,
  'entity-ids': Schema.Array(Schema.String),
  rule: Schema.optional(Schema.Record({ key: Schema.String, value: Schema.String })),
  groups: Schema.optional(Schema.Array(Schema.suspend(() => AuthoredGroupingSchema))),
  stereotype: Schema.optional(Schema.String),
})
