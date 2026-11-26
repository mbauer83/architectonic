/**
 * Draws a piece of PlantUML's own drawing, as the canvas's geometry hands it over: an outline, a glyph,
 * words, a line, a decoration — with the attributes PlantUML gave them, so the canvas looks as the
 * composed picture does.
 *
 * Only drawing passes: an element that is not one a rendered shape or line is drawn with is left
 * out, as is any attribute that would run something or fetch something. The backend lets through
 * the same elements and no others.
 */
import type { PropType, VNode } from 'vue'
import { defineComponent, h } from 'vue'
import type { DrawingNode } from '../../../domain/schemas/diagramLayoutGeometry'

/** What a rendered shape or line is drawn with. */
const DRAWING_TAGS = new Set(['g', 'rect', 'path', 'polygon', 'polyline', 'ellipse', 'line', 'text', 'image'])

/** An image draws only what it carries in itself; nothing is fetched and nothing is run. */
const isLink = (name: string): boolean => name === 'href' || name === 'xlink:href'
const keeps = (name: string, value: string): boolean =>
  !/^on/i.test(name) && (!isLink(name) || value.startsWith('data:image/'))

export const drawnAttributes = (node: DrawingNode): Record<string, string> =>
  Object.fromEntries(Object.entries(node.attributes).filter(([name, value]) => keeps(name, value)))

export const drawn = (node: DrawingNode): VNode | null => {
  if (!DRAWING_TAGS.has(node.tag)) return null
  const children = node.children.map(drawn).filter((child): child is VNode => child !== null)
  return h(node.tag, drawnAttributes(node), node.text === undefined ? children : [node.text, ...children])
}

/**
 * The nodes, drawn in order inside one group that *transform* places. A component of its own rather than
 * a function, so a drawing whose nodes and place did not change is not drawn again when the canvas is:
 * a drag frame redraws the few pieces that moved, not a picture of hundreds (`one` keeps the nodes the
 * same array from frame to frame).
 */
const CanvasDrawn = defineComponent({
  name: 'CanvasDrawn',
  props: {
    nodes: { type: Array as PropType<readonly DrawingNode[]>, required: true },
    transform: { type: String, default: undefined },
  },
  setup: (props) => () =>
    h(
      'g',
      props.transform ? { transform: props.transform } : {},
      props.nodes.map(drawn).filter((child): child is VNode => child !== null),
    ),
})

const alone = new WeakMap<DrawingNode, readonly DrawingNode[]>()

/** *node* as the nodes `CanvasDrawn` draws: the same array for the same node, every time it is asked. */
export const one = (node: DrawingNode): readonly DrawingNode[] => {
  const known = alone.get(node)
  if (known) return known
  const nodes = [node]
  alone.set(node, nodes)
  return nodes
}

export default CanvasDrawn
