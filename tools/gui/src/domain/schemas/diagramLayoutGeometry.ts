/**
 * The picture a diagram is arranged on (`GET /api/diagrams/{id}/layout/geometry`): PlantUML's own
 * picture of it, read by the backend's one reader of it, with each shape and line named as a layout
 * names it and carried with PlantUML's own drawing — and the layout the diagram states, if any.
 *
 * The answer omits what is absent rather than sending null, so every "may be absent" here is an
 * optional key.
 */
import { Schema } from 'effect'
import type { Extent, Point } from '../layout/geometry'
import { DiagramLayoutSchema } from './diagramLayout'

const ExtentSchema = Schema.Struct({
  left: Schema.Number,
  top: Schema.Number,
  right: Schema.Number,
  bottom: Schema.Number,
})

/**
 * A piece of PlantUML's own drawing — an outline, a glyph, a word, a line, a decoration — as a tree.
 * An editor draws with it rather than with a palette of its own: the colours, strokes, glyphs and
 * fonts are the ones PlantUML drew, the ones the composer places.
 */
export interface DrawingNode {
  readonly tag: string
  readonly attributes: { readonly [name: string]: string }
  readonly text?: string
  readonly children: readonly DrawingNode[]
}

export const DrawingNodeSchema: Schema.Schema<DrawingNode> = Schema.Struct({
  tag: Schema.String,
  attributes: Schema.Record({ key: Schema.String, value: Schema.String }),
  text: Schema.optional(Schema.String),
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
  /** At the source end, then the target end: the order the course runs. */
  ends: Schema.Tuple(LineEndSchema, LineEndSchema),
  label: Schema.optional(Schema.Struct({ texts: Schema.Array(DrawingNodeSchema), centre: PairSchema })),
})

const MeasuredWordSchema = Schema.Struct({
  text: Schema.String,
  x: Schema.Number,
  y: Schema.Number,
  width: Schema.Number,
})

const GeometryElementSchema = Schema.Struct({
  alias: Schema.String,
  key: Schema.optional(Schema.String),
  label: Schema.String,
  extent: ExtentSchema,
  inside: Schema.optional(Schema.String),
  words: Schema.Array(MeasuredWordSchema),
  outside_label: Schema.optional(ExtentSchema),
  /** The narrowest it may be sized: its longest word, and its first word after its glyph, padded as its
   * label is when it is set again. Absent where it has no label. */
  least_width: Schema.optional(Schema.Number),
  drawing: DrawingNodeSchema,
})

const GeometryBoxSchema = Schema.Struct({
  alias: Schema.String,
  kind: Schema.Literal('domain', 'type', 'authored-grouping', 'element'),
  section: Schema.Literal('elements', 'boxes'),
  key: Schema.optional(Schema.String),
  label: Schema.String,
  extent: ExtentSchema,
  inside: Schema.optional(Schema.String),
  words: Schema.Array(MeasuredWordSchema),
  title_band: Schema.optional(ExtentSchema),
  /** What a box the renderer computes admits, written as a stated grouping's rule is: one of
   * `domain` or `type` to the name it selects. Absent for any other box. */
  rule: Schema.optional(Schema.Record({ key: Schema.String, value: Schema.String })),
  drawing: DrawingNodeSchema,
})

const GeometryRelationSchema = Schema.Struct({
  index: Schema.Number,
  key: Schema.optional(Schema.String),
  source: Schema.String,
  target: Schema.String,
  decorated: Schema.Tuple(Schema.Boolean, Schema.Boolean),
  course: Schema.Array(PairSchema),
  label: Schema.String,
  label_size: Schema.optional(PairSchema),
  drawing: LineDrawingSchema,
})

/** A part PlantUML draws round the diagram — its title, its legend — and where it is drawn. */
const SurroundPartSchema = Schema.Struct({ drawing: DrawingNodeSchema, extent: ExtentSchema })

/** What PlantUML draws round the diagram, and what the diagram occupied when it was drawn. */
const SurroundSchema = Schema.Struct({ drawn: ExtentSchema, parts: Schema.Array(SurroundPartSchema) })

export type Surround = typeof SurroundSchema.Type
export type SurroundPart = typeof SurroundPartSchema.Type

export const DiagramLayoutGeometrySchema = Schema.Struct({
  artifact_id: Schema.String,
  name: Schema.String,
  canvas: ExtentSchema,
  /** What PlantUML draws behind everything: the background. */
  backdrop: Schema.Array(DrawingNodeSchema),
  /** What PlantUML draws round the diagram: its title and its legend. */
  surround: SurroundSchema,
  elements: Schema.Array(GeometryElementSchema),
  boxes: Schema.Array(GeometryBoxSchema),
  relations: Schema.Array(GeometryRelationSchema),
  /** The layout the diagram states; absent where PlantUML arranges it. */
  layout: Schema.optional(DiagramLayoutSchema),
  /** The revision of the stored diagram this picture is drawn from, which a save sends back (`base_revision`);
   * absent for a picture of no stored diagram. */
  revision: Schema.optional(Schema.String),
})

/** How far each part drawn round the diagram moves, in the order asked (`layout/surround/preview`). */
export const SurroundPlacementSchema = Schema.Struct({
  moves: Schema.Array(Schema.Tuple(Schema.Number, Schema.Number)),
})

/** Each resized shape drawn by the composer at its new size, in the order asked. */
export const ShapeDrawingsSchema = Schema.Struct({ drawings: Schema.Array(DrawingNodeSchema) })

/** What a layout patch did, and the layout block the diagram holds after it (empty: none). */
export const DiagramLayoutPatchResultSchema = Schema.Struct({
  artifact_id: Schema.String,
  wrote: Schema.Boolean,
  warnings: Schema.Array(Schema.String),
  errors: Schema.Array(Schema.String),
  layout: DiagramLayoutSchema,
})

export type LayoutGeometry = typeof DiagramLayoutGeometrySchema.Type
export type GeometryElement = typeof GeometryElementSchema.Type
export type GeometryBox = typeof GeometryBoxSchema.Type
export type GeometryRelation = typeof GeometryRelationSchema.Type
export type MeasuredWord = typeof MeasuredWordSchema.Type
export type LineDrawing = typeof LineDrawingSchema.Type
export type LineEnd = typeof LineEndSchema.Type
export type DiagramLayoutPatchResult = typeof DiagramLayoutPatchResultSchema.Type

/** A shape of the picture, element or box: what moving and resizing ask of either. */
export interface GeometryShape {
  readonly alias: string
  readonly extent: Extent
  readonly inside?: string
}

export const pointsOf = (course: readonly (readonly [number, number])[]): Point[] =>
  course.map(([x, y]) => ({ x, y }))
