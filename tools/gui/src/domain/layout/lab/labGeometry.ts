/**
 * What the layout lab is given: PlantUML's own picture of a diagram, read by the backend's one reader
 * of it, with each shape and line named as a layout names it.
 *
 * Not part of the REST contract: the lab's routes are outside `/api` and outside the published
 * document, served only while the lab is switched on, so this decoder is held to the lab's own route
 * (`src/infrastructure/rest/layout_lab/geometry.py`) rather than to the generated types.
 */
import { Schema } from 'effect'
import type { Extent, Point } from '../geometry'

const ExtentSchema = Schema.Struct({
  left: Schema.Number,
  top: Schema.Number,
  right: Schema.Number,
  bottom: Schema.Number,
})

const WordSchema = Schema.Struct({
  text: Schema.String,
  x: Schema.Number,
  y: Schema.Number,
  width: Schema.Number,
})

const ElementSchema = Schema.Struct({
  alias: Schema.String,
  key: Schema.NullOr(Schema.String),
  label: Schema.String,
  extent: ExtentSchema,
  inside: Schema.NullOr(Schema.String),
  words: Schema.Array(WordSchema),
  outside_label: Schema.NullOr(ExtentSchema),
})

const BoxSchema = Schema.Struct({
  alias: Schema.String,
  kind: Schema.Literal('domain', 'type', 'authored-grouping', 'element'),
  section: Schema.Literal('elements', 'boxes'),
  key: Schema.NullOr(Schema.String),
  label: Schema.String,
  extent: ExtentSchema,
  inside: Schema.NullOr(Schema.String),
  words: Schema.Array(WordSchema),
  title_band: Schema.NullOr(ExtentSchema),
})

const RelationSchema = Schema.Struct({
  index: Schema.Number,
  key: Schema.NullOr(Schema.String),
  source: Schema.String,
  target: Schema.String,
  decorated: Schema.Tuple(Schema.Boolean, Schema.Boolean),
  course: Schema.Array(Schema.Tuple(Schema.Number, Schema.Number)),
  label: Schema.String,
  label_size: Schema.NullOr(Schema.Tuple(Schema.Number, Schema.Number)),
})

export const LabGeometrySchema = Schema.Struct({
  artifact_id: Schema.String,
  name: Schema.String,
  canvas: ExtentSchema,
  elements: Schema.Array(ElementSchema),
  boxes: Schema.Array(BoxSchema),
  relations: Schema.Array(RelationSchema),
})

export type LabGeometry = typeof LabGeometrySchema.Type
export type LabElement = typeof ElementSchema.Type
export type LabBox = typeof BoxSchema.Type
export type LabRelation = typeof RelationSchema.Type
export type LabWord = typeof WordSchema.Type

/** A shape of the picture, element or box: what moving and resizing ask of either. */
export interface LabShape {
  readonly alias: string
  readonly extent: Extent
  readonly inside: string | null
}

export const pointsOf = (course: readonly (readonly [number, number])[]): Point[] =>
  course.map(([x, y]) => ({ x, y }))
