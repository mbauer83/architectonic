import { Schema } from 'effect'

/** Where a shape's top-left corner sits, and its size where the diagram states one. */
const LayoutPlacedSchema = Schema.Struct({
  x: Schema.Number,
  y: Schema.Number,
  w: Schema.optional(Schema.Number),
  h: Schema.optional(Schema.Number),
})

/** Where a relation attaches: a side of its element and a fraction along it, from the top or left. */
const LayoutPortSchema = Schema.Struct({
  side: Schema.Literal('top', 'right', 'bottom', 'left'),
  at: Schema.Number,
})

/**
 * A diagram's stated layout: geometry only, keyed by the identities the diagram already uses —
 * `elements` by instance id, `boxes` by grouping id or rule key, `relations` by the key `edge_key`
 * serves. Decoded so a read is typed; nothing in this app draws from it yet.
 */
export const DiagramLayoutSchema = Schema.Struct({
  grid: Schema.optional(Schema.Number),
  elements: Schema.optional(Schema.Record({ key: Schema.String, value: LayoutPlacedSchema })),
  boxes: Schema.optional(Schema.Record({ key: Schema.String, value: LayoutPlacedSchema })),
  relations: Schema.optional(Schema.Record({
    key: Schema.String,
    value: Schema.Struct({
      from: Schema.optional(LayoutPortSchema),
      to: Schema.optional(LayoutPortSchema),
      via: Schema.optional(Schema.Array(Schema.Tuple(Schema.Number, Schema.Number))),
      label: Schema.optional(Schema.Struct({ at: Schema.Number, dx: Schema.Number, dy: Schema.Number })),
    }),
  })),
  z: Schema.optional(Schema.Record({ key: Schema.String, value: Schema.Number })),
})
