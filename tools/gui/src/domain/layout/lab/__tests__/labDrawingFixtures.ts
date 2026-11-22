/**
 * Drawings for lab geometry built by hand in tests: what a shape or line is drawn with, where the test
 * is about where it goes and not how it looks.
 */
import type { DrawingNode, LineDrawing } from '../../../schemas/diagramLayoutGeometry'

export const drawingNode = (tag: string, attributes: Record<string, string> = {}): DrawingNode =>
  ({ tag, attributes, text: undefined, children: [] })

/** A shape's drawing: an empty group. */
export const SHAPE_DRAWING: DrawingNode = drawingNode('g')

/** A line's drawing with no decoration at either end and no label. */
export const LINE_DRAWING: LineDrawing = {
  group: drawingNode('g'),
  line: drawingNode('path', { d: 'M0,0' }),
  ends: [
    { marks: [], at: [0, 0], heading: [1, 0], gap: 0 },
    { marks: [], at: [0, 0], heading: [1, 0], gap: 0 },
  ],
  label: undefined,
}
