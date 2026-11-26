import { Schema } from 'effect'

/** What only a hand-drawn picture has (`hand_drawn` on the diagram read): boxes by their labels, elements by
 * their names, relations by the names of their ends and the model's type for them. Never PlantUML aliases. */
export const HandDrawnSchema = Schema.Struct({
  boxes: Schema.Array(Schema.String),
  elements: Schema.Array(Schema.String),
  relations: Schema.Array(Schema.Struct({
    source: Schema.String,
    target: Schema.String,
    type: Schema.optional(Schema.String),
  })),
  directions: Schema.Array(Schema.String),
})
export type HandDrawn = typeof HandDrawnSchema.Type
