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

/**
 * A piece of PlantUML's own drawing — an outline, a glyph, a word, a line, a decoration — as a tree.
 * The lab draws with it rather than with a palette of its own: the colours, strokes, glyphs and
 * fonts are the ones PlantUML drew, the ones the composer places.
 */
export interface DrawingNode {
  readonly tag: string
  readonly attributes: { readonly [name: string]: string }
  readonly text: string | null
  readonly children: readonly DrawingNode[]
}

export const DrawingNodeSchema: Schema.Schema<DrawingNode> = Schema.Struct({
  tag: Schema.String,
  attributes: Schema.Record({ key: Schema.String, value: Schema.String }),
  text: Schema.NullOr(Schema.String),
  children: Schema.Array(Schema.suspend((): Schema.Schema<DrawingNode> => DrawingNodeSchema)),
})

const PairSchema = Schema.Tuple(Schema.Number, Schema.Number)

/** One end of a line: its decorations, and the frame they were drawn in — where, facing which way. */
const LineEndSchema = Schema.Struct({
  marks: Schema.Array(DrawingNodeSchema),
  at: PairSchema,
  heading: PairSchema,
  /** How far short of the end the line itself stops: the run a hollow head's base sits back by. */
  gap: Schema.Number,
})

/** How a line is drawn: PlantUML's whole drawing of it, and its parts for drawing it along a new course. */
const LineDrawingSchema = Schema.Struct({
  group: DrawingNodeSchema,
  line: DrawingNodeSchema,
  /** At the source end, then the target end: the order the lab's course runs. */
  ends: Schema.Tuple(LineEndSchema, LineEndSchema),
  label: Schema.NullOr(Schema.Struct({ texts: Schema.Array(DrawingNodeSchema), centre: PairSchema })),
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
  drawing: DrawingNodeSchema,
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
  drawing: DrawingNodeSchema,
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
  drawing: LineDrawingSchema,
})

export const LabGeometrySchema = Schema.Struct({
  artifact_id: Schema.String,
  name: Schema.String,
  canvas: ExtentSchema,
  /** What PlantUML draws behind everything: the background. */
  backdrop: Schema.Array(DrawingNodeSchema),
  elements: Schema.Array(ElementSchema),
  boxes: Schema.Array(BoxSchema),
  relations: Schema.Array(RelationSchema),
})

export type LabGeometry = typeof LabGeometrySchema.Type
export type LabElement = typeof ElementSchema.Type
export type LabBox = typeof BoxSchema.Type
export type LabRelation = typeof RelationSchema.Type
export type LabWord = typeof WordSchema.Type
export type LabLineDrawing = typeof LineDrawingSchema.Type
export type LabLineEnd = typeof LineEndSchema.Type

/** A shape of the picture, element or box: what moving and resizing ask of either. */
export interface LabShape {
  readonly alias: string
  readonly extent: Extent
  readonly inside: string | null
}

export const pointsOf = (course: readonly (readonly [number, number])[]): Point[] =>
  course.map(([x, y]) => ({ x, y }))
