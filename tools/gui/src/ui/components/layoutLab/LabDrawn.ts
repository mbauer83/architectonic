/**
 * Draws a piece of PlantUML's own drawing, as the lab's geometry hands it over: an outline, a glyph,
 * words, a line, a decoration — with the attributes PlantUML gave them, so the lab looks as the
 * composed picture does.
 *
 * Only drawing passes: an element that is not one a rendered shape or line is drawn with is left
 * out, as is any attribute that would run something or fetch something. The backend lets through
 * the same elements and no others.
 */
import type { FunctionalComponent, VNode } from 'vue'
import { h } from 'vue'
import type { DrawingNode } from '../../../domain/layout/lab/labGeometry'

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
  return h(node.tag, drawnAttributes(node), node.text === null ? children : [node.text, ...children])
}

/** The nodes, drawn in order inside one group that *transform* places. */
const LabDrawn: FunctionalComponent<{ nodes: readonly DrawingNode[]; transform?: string }> = (props) =>
  h(
    'g',
    props.transform ? { transform: props.transform } : {},
    props.nodes.map(drawn).filter((child): child is VNode => child !== null),
  )

LabDrawn.props = ['nodes', 'transform']

export default LabDrawn
