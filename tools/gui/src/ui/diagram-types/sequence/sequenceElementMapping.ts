import type { DiagramMapContext, DiagramElementMap } from '../../lib/diagramViewerExtensions'
import { graphvizMapElements } from '../../lib/graphvizElementMapping'

/**
 * Local message ids (authored array order) that actually rendered a message arrow.
 *
 * A message with no complete `seq-from`/`seq-to` pair renders as a PUML comment (no SVG
 * `<g class="message">` group) — see `_emit_message` in the sequence renderer — so it must be
 * excluded here or positional zipping against the DOM would drift out of alignment.
 */
function renderedMessageIds(diagramEntities: Record<string, unknown>): string[] {
  const messages = Array.isArray(diagramEntities.message)
    ? (diagramEntities.message as Array<Record<string, unknown>>)
    : []
  const conns = Array.isArray(diagramEntities._connections)
    ? (diagramEntities._connections as Array<Record<string, unknown>>)
    : []
  const hasFrom = new Set<string>()
  const hasTo = new Set<string>()
  for (const c of conns) {
    const source = typeof c.source === 'string' ? c.source : ''
    if (!source) continue
    if (c.conn_type === 'seq-from') hasFrom.add(source)
    if (c.conn_type === 'seq-to') hasTo.add(source)
  }
  return messages
    .map((m) => (typeof m.id === 'string' ? m.id : ''))
    .filter((id) => id && hasFrom.has(id) && hasTo.has(id))
}

/**
 * Map each rendered message arrow to its message entity's artifact id by DOM order.
 *
 * PlantUML gives message groups no id/attribute tying them back to our local message id, so
 * order is the only reliable signal: the renderer emits `<g class="message">` in the same
 * top-to-bottom order as the `message` array (`_emit_messages_with_groupings`), and the array
 * order is itself the sequence order.
 */
function mapMessageNodes(
  svgRoot: SVGSVGElement,
  ctx: DiagramMapContext,
  nodes: Map<string, Element[]>,
): void {
  const diagramEntities = ctx.diagramEntities
  if (!diagramEntities) return
  const orderedIds = renderedMessageIds(diagramEntities)
  if (!orderedIds.length) return

  const artifactIdByLocalId = new Map<string, string>()
  for (const e of ctx.entities) {
    if (e.artifact_type === 'message' && e.display_alias) artifactIdByLocalId.set(e.display_alias, e.artifact_id)
  }

  const groups = Array.from(svgRoot.querySelectorAll<SVGGElement>('g.message'))
  orderedIds.forEach((localId, i) => {
    const g = groups[i]
    const artifactId = artifactIdByLocalId.get(localId)
    if (!g || !artifactId) return
    const list = nodes.get(artifactId)
    if (list) list.push(g)
    else nodes.set(artifactId, [g])
  })
}

/**
 * Sequence diagrams: lifelines are aliased by their bound entity's (or, if unbound, their own
 * local id's) normalized `display_alias`, so the graphviz default already resolves them via
 * PlantUML's `data-qualified-name` attribute. Messages carry no such anchor and are mapped here
 * by DOM order instead.
 */
export function sequenceMapElements(svgRoot: SVGSVGElement, ctx: DiagramMapContext): DiagramElementMap {
  const { nodes, edges } = graphvizMapElements(svgRoot, ctx)
  mapMessageNodes(svgRoot, ctx, nodes)
  return { nodes, edges }
}
