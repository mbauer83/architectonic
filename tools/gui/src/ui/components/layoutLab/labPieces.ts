/**
 * The layout lab's picture as pieces to draw: each shape and line where it is now, drawn as PlantUML
 * or the composer drew it, and the paint order (`labPaintOrder`) turned into those pieces.
 */
import type { Extent } from '../../../domain/layout/geometry'
import type { DrawingNode, LabGeometry } from '../../../domain/layout/lab/labGeometry'
import type { DrawnLine } from '../../../domain/layout/lab/labLineDrawing'
import { drawnLine } from '../../../domain/layout/lab/labLineDrawing'
import type { Placement } from '../../../domain/layout/lab/labRouting'
import type { PlacedDrawing } from '../../../domain/layout/lab/labShapeDrawing'
import { shapeDrawing } from '../../../domain/layout/lab/labShapeDrawing'
import { dragRegionOf } from './labDrawing'
import type { Painted } from './labPaintOrder'

export interface DrawnShape {
  readonly alias: string
  readonly isBox: boolean
  /** Where it is taken to drag it: the whole outline, a grouping's full-width title band included. */
  readonly region: Extent
  readonly drawing: PlacedDrawing
}

export interface DrawnRelation {
  /** PlantUML's own drawing of the whole relation, label and decorations in it, until the first change. */
  readonly asDrawn: DrawingNode | null
  readonly along: DrawnLine
}

/** One piece of the picture, ready to draw. */
export type Piece =
  | { readonly kind: 'shape'; readonly key: string; readonly shape: DrawnShape }
  | { readonly kind: 'line'; readonly key: string; readonly relation: number; readonly drawn: DrawnRelation }
  | {
    readonly kind: 'label'; readonly key: string; readonly relation: number
    readonly label: NonNullable<DrawnLine['label']>
  }

type Reshaped = ReadonlyMap<string, NonNullable<Parameters<typeof shapeDrawing>[3]>>
type Courses = ReadonlyMap<number, Parameters<typeof drawnLine>[1]>

/** Every shape, by alias, where it is now, drawn as PlantUML or the composer drew it. */
export const drawnShapes = (
  drawn: LabGeometry, where: Placement, reshaped: Reshaped,
): ReadonlyMap<string, DrawnShape> => {
  const all = [
    ...drawn.boxes.map((shape) => ({ shape, isBox: true })),
    ...drawn.elements.map((shape) => ({ shape, isBox: false })),
  ]
  return new Map(all.flatMap(({ shape, isBox }): [string, DrawnShape][] => {
    const now = isBox ? where.boxes.get(shape.alias) : where.elements.get(shape.alias)
    if (!now) return []
    const drawing = shapeDrawing(shape.extent, shape.drawing, now, reshaped.get(shape.alias))
    return [[shape.alias, { alias: shape.alias, isBox, region: dragRegionOf(now), drawing }]]
  }))
}

/** Each line, by its place: PlantUML's own until the first change, then drawn along the router's course. */
export const drawnRelations = (
  drawn: LabGeometry, courses: Courses, asDrawn: boolean,
): ReadonlyMap<number, DrawnRelation> =>
  new Map(drawn.relations.flatMap((relation): [number, DrawnRelation][] => {
    const course = courses.get(relation.index)
    if (!course || course.length < 2) return []
    const along = drawnLine(relation.drawing, course)
    return [[relation.index, { asDrawn: asDrawn ? relation.drawing.group : null, along }]]
  }))

/** What *painted* draws, if anything: a label drawn inside PlantUML's own relation has no piece of its own. */
export const pieceOf = (
  painted: Painted, shapes: ReadonlyMap<string, DrawnShape>, lines: ReadonlyMap<number, DrawnRelation>,
): Piece[] => {
  if (painted.kind === 'shape') {
    const shape = shapes.get(painted.alias)
    return shape ? [{ kind: 'shape', key: `shape:${painted.alias}`, shape }] : []
  }
  const drawn = lines.get(painted.relation)
  if (!drawn) return []
  const relation = painted.relation
  if (painted.kind === 'line') return [{ kind: 'line', key: `line:${relation}`, relation, drawn }]
  const label = drawn.asDrawn === null ? drawn.along.label : null
  return label ? [{ kind: 'label', key: `label:${relation}`, relation, label }] : []
}
