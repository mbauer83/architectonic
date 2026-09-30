import { Schema } from 'effect'
import { BaselineStandingSchema } from './baselineStanding'

/**
 * The icon library, and which icon each instance of a diagram shows.
 *
 * An icon row describes what a picker chooses by — name, what it applies to, tags, whose mark it is —
 * and never carries its picture: that is served as bytes at `/api/icons/{id}/image`. The preview is
 * the exception, because it answers for icons a diagram holds for itself, which have no address.
 */

export const IconStyleSchema = Schema.Literal('badge', 'figure')
export type IconStyle = typeof IconStyleSchema.Type

export const IconSummarySchema = Schema.Struct({
  artifact_id: Schema.String,
  name: Schema.String,
  attribution: Schema.String,
  /** Type and specialization names it may be shown on; empty means any element. */
  applies_to: Schema.Array(Schema.String),
  default_style: IconStyleSchema,
  tags: Schema.Array(Schema.String),
  status: Schema.Literal('active', 'retired'),
  source_format: Schema.Literal('svg', 'png', 'jpeg', 'webp'),
  width: Schema.Number,
  height: Schema.Number,
  render_digest: Schema.String,
  is_global: Schema.Boolean,
  baseline_standing: BaselineStandingSchema,
  /** The diagrams naming it, for an instance or for a type. */
  used_on: Schema.Array(Schema.Struct({ artifact_id: Schema.String, name: Schema.String })),
  /** The specializations whose default it is. */
  default_for: Schema.Array(Schema.String),
})
export type IconSummary = typeof IconSummarySchema.Type

/** An icon a picker offers, and whether a diagram already shows it for the element being chosen for. */
export const OfferedIconSchema = Schema.Struct({
  ...IconSummarySchema.fields,
  shown_for_element: Schema.Boolean,
})
export type OfferedIcon = typeof OfferedIconSchema.Type

export const IconListSchema = Schema.Struct({
  total: Schema.Number,
  items: Schema.Array(OfferedIconSchema),
})
export type IconList = typeof IconListSchema.Type

/** The icon one instance shows, and which statement decided it. */
export const ShownIconSchema = Schema.Struct({
  /** As the deciding statement names it: `ICO@…` for the library's, `local:<key>` for the diagram's. */
  icon: Schema.String,
  style: IconStyleSchema,
  level: Schema.Literal('instance', 'type', 'specialization-default'),
  /** Its render digest: the key of its picture in `pictures`. */
  picture: Schema.String,
})
export type ShownIcon = typeof ShownIconSchema.Type

export const ShownIconsSchema = Schema.Struct({
  /** Instance id → its icon; an instance that shows its type glyph is absent. */
  icons: Schema.Record({ key: Schema.String, value: ShownIconSchema }),
  /** Render digest → the picture as a `data:image/png;base64,…` URL. */
  pictures: Schema.Record({ key: Schema.String, value: Schema.String }),
  /**
   * Instance id → the type the diagram draws it as, where its projection draws a model entity as a type
   * of its own (a C4 container): the name an "every element of this type" statement is made under.
   */
  drawn_as: Schema.Record({ key: Schema.String, value: Schema.String }),
})
export type ShownIcons = typeof ShownIconsSchema.Type
