import { nextTick, onUnmounted, type Ref } from 'vue'
import { stripMarkerAttributes } from '../lib/svgHitAreas'
import {
  type AssuranceDiagramEdge,
  type AssuranceDiagramNode,
  type NodeRepresentingEdge,
} from '../components/AssuranceDiagramPanel.helpers'

/**
 * Wires click-to-select onto a rendered assurance SVG: tags node groups with
 * `data-assurance-node-id`, adds a fat transparent hit-stroke to edge groups, and
 * routes clicks to the supplied selection callbacks. Listeners are scoped to an
 * AbortController that is replaced on every (re-)attach and aborted on unmount, so
 * re-rendering the SVG never leaks stale handlers.
 *
 * It also marks the current selection on the SVG. Selection lives in the host, but the *DOM*
 * expression of it belongs here, next to the tagging that makes the elements findable: without
 * it, clicking a node opened a detail panel while the diagram gave no sign of which node the
 * panel was describing.
 */

/** Class the stylesheet keys the selected-node/edge highlight off. */
export const SELECTED_CLASS = 'svg-assurance-selected'
function addEdgeHitArea(group: SVGGElement): void {
  for (const segment of Array.from(group.querySelectorAll<SVGElement>('path, line, polyline'))) {
    const hit = segment.cloneNode(false) as SVGElement
    stripMarkerAttributes(hit)
    hit.setAttribute('fill', 'none')
    hit.setAttribute('stroke', 'transparent')
    hit.setAttribute('stroke-width', '12')
    hit.setAttribute('pointer-events', 'stroke')
    group.appendChild(hit)
  }
}

export function useAssuranceSvgInteractions(opts: {
  svgContainer: Ref<HTMLElement | null>
  nodes: Ref<AssuranceDiagramNode[]>
  edges: Ref<AssuranceDiagramEdge[]>
  /**
   * `{ alias: node_id }`, as published by the renderer that wrote the PUML. Supplied rather than
   * derived: the alias is the renderer's naming rule, and a client that reconstructs it is a second
   * implementation of a cross-language contract. The two once disagreed by a single `N_` prefix and
   * every shape in a bowtie became inert — no error, no log, just nothing happening on click.
   */
  nodeAliases: Ref<Record<string, string>>
  /** Edges that draw a node; a click on one selects that node, not an edge. */
  nodeRepresentingEdges?: Ref<NodeRepresentingEdge[]>
  onSelectNode: (nodeId: string) => void
  onSelectEdge: (edge: AssuranceDiagramEdge) => void
}) {
  let controller: AbortController | null = null

  /** Mark the selected node or edge, clearing whatever was marked before. Safe to call before
   * the SVG exists or after it is replaced — a re-render simply has nothing marked yet. */
  function markSelection(selection: { nodeId?: string | null; edgeId?: string | null }): void {
    const svgElement = opts.svgContainer.value?.querySelector('svg')
    if (!svgElement) return
    // Compared attribute-by-attribute rather than through a built selector: assurance ids
    // contain `@`, `.` and `:`, all of which are selector syntax.
    const tagged = svgElement.querySelectorAll('[data-assurance-node-id], [data-assurance-edge-id]')
    for (const group of Array.from(tagged)) {
      const isSelected =
        (selection.nodeId != null && group.getAttribute('data-assurance-node-id') === selection.nodeId)
        || (selection.edgeId != null && group.getAttribute('data-assurance-edge-id') === selection.edgeId)
      group.classList.toggle(SELECTED_CLASS, isSelected)
    }
  }

  async function attachInteractivity(): Promise<void> {
    controller?.abort()
    controller = new AbortController()
    const { signal } = controller
    await nextTick()
    const svgElement = opts.svgContainer.value?.querySelector('svg')
    if (!svgElement) return
    const aliases = new Map(Object.entries(opts.nodeAliases.value))
    const aliasFor = (nodeId: string): string | undefined =>
      [...aliases].find(([, id]) => id === nodeId)?.[0]
    const svgIdToAlias = new Map<string, string>()

    for (const group of Array.from(svgElement.querySelectorAll<SVGGElement>('g'))) {
      const candidates = [
        group.getAttribute('data-entity'),
        group.id.startsWith('entity_') ? group.id.slice(7) : group.id,
        group.getAttribute('data-qualified-name')?.split('.').pop(),
        group.querySelector(':scope > title')?.textContent?.trim(),
      ]
      const alias = candidates.find((candidate) => candidate && aliases.has(candidate))
      if (!alias) continue
      if (group.id) svgIdToAlias.set(group.id, alias)
      group.setAttribute('data-assurance-node-id', aliases.get(alias)!)
      group.addEventListener('click', (event) => {
        event.stopPropagation()
        opts.onSelectNode(aliases.get(alias)!)
      }, { signal })
    }

    // An edge that draws a node is tagged as a NODE, so selecting it, highlighting it, and
    // opening its detail all work through the same path as selecting a shape would.
    const nodeByPair = new Map<string, string>()
    for (const edge of opts.nodeRepresentingEdges?.value ?? []) {
      const source = aliasFor(edge.source_id)
      const target = aliasFor(edge.target_id)
      if (source && target) nodeByPair.set(`${source}:${target}`, edge.node_id)
    }

    const edgeByPair = new Map<string, AssuranceDiagramEdge>()
    for (const edge of opts.edges.value) {
      const source = aliasFor(edge.source_id)
      const target = aliasFor(edge.target_id)
      if (!source || !target) continue
      edgeByPair.set(`${source}:${target}`, edge)
      edgeByPair.set(`${target}:${source}`, edge)
    }
    for (const group of Array.from(svgElement.querySelectorAll<SVGGElement>('g[data-entity-1]'))) {
      const rawSource = group.getAttribute('data-entity-1') ?? ''
      const rawTarget = group.getAttribute('data-entity-2') ?? ''
      const source = svgIdToAlias.get(rawSource) ?? rawSource
      const target = svgIdToAlias.get(rawTarget) ?? rawTarget
      // Direction matters: only the authored direction draws the node, so the reverse arrow (a
      // control structure's feedback, for instance) stays an ordinary edge.
      const actionId = nodeByPair.get(`${source}:${target}`)
      if (actionId) {
        addEdgeHitArea(group)
        group.setAttribute('data-assurance-node-id', actionId)
        group.addEventListener('click', (event) => {
          event.stopPropagation()
          opts.onSelectNode(actionId)
        }, { signal })
        continue
      }
      const edge = edgeByPair.get(`${source}:${target}`)
      if (!edge) continue
      addEdgeHitArea(group)
      group.setAttribute('data-assurance-edge-id', edge.edge_id ?? `${edge.source_id}:${edge.target_id}`)
      group.addEventListener('click', (event) => {
        event.stopPropagation()
        opts.onSelectEdge(edge)
      }, { signal })
    }
  }

  onUnmounted(() => controller?.abort())

  return { attachInteractivity, markSelection }
}
