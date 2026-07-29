/**
 * The assurance vocabulary the treemap needs: how a node is grouped, coloured and weighed.
 *
 * The counterpart of `lib/domains` for the architecture treemap. It lives beside the assurance
 * component rather than inside the shared `Treemap`, because a treemap that knew what a hazard was
 * would be one the architecture surface could not use — and that boundary is the reason the shared
 * component exists at all.
 *
 * **Grouped by node type, not by concern class.** The type is what an analyst navigates by ("what
 * hazards are there") and every node has one; concern class is optional and empty on most nodes, so
 * grouping by it would put the majority in one anonymous bucket.
 *
 * **Sized by connection count**, exactly as the architecture treemap is. In an assurance graph that
 * reads as "how much of the analysis hangs off this" — a hazard reached by six failure modes and
 * leading to two losses is load-bearing, and a treemap is the one view that says so at a glance.
 * The scale is the reader's visible edge set, so it never implies an above-ceiling neighbour.
 */

import { groupLeaves, type TreemapGroup, type TreemapLeaf } from './Treemap.helpers'

export interface AssuranceTreemapNode {
  node_id: string
  node_type: string
  name: string
  conn_in?: number
  conn_out?: number
}

/**
 * Colour per node type, warm for the things that go wrong and cool for the things that answer them.
 *
 * Related types sit near each other on purpose: losses and hazards are the consequence spine,
 * UCAs and failure modes are causes, constraints and evidence are the response. A reader who has
 * not read a legend still sees three families.
 */
const TYPE_COLORS: Record<string, string> = {
  loss: '#b91c1c',
  hazard: '#dc2626',
  'loss-scenario': '#ea580c',
  'unsafe-control-action': '#f59e0b',
  'failure-mode': '#d97706',
  risk: '#a16207',
  'control-structure-node': '#2563eb',
  'control-action': '#3b82f6',
  feedback: '#0ea5e9',
  'assurance-constraint': '#059669',
  evidence: '#10b981',
  obligation: '#0d9488',
  'corrective-action': '#14b8a6',
  incident: '#7c3aed',
}

/** Grey for a type this build has no colour for — visibly unclassified rather than miscoloured. */
export const UNKNOWN_TYPE_COLOR = '#94a3b8'

export const nodeTypeColor = (nodeType: string): string =>
  TYPE_COLORS[nodeType] ?? UNKNOWN_TYPE_COLOR

/** Reader-facing group heading for a node type: the slug, spaced out. */
export const nodeTypeLabel = (nodeType: string): string =>
  nodeType ? nodeType.replace(/-/g, ' ').replace(/^./, (c) => c.toUpperCase()) : 'Untyped'

export const connectionTotal = (node: AssuranceTreemapNode): number =>
  (node.conn_in ?? 0) + (node.conn_out ?? 0)

export const assuranceTreemapGroups = (
  nodes: readonly AssuranceTreemapNode[],
): TreemapGroup[] =>
  groupLeaves(
    nodes,
    (node): TreemapLeaf => {
      const connections = connectionTotal(node)
      return {
        key: node.node_id,
        label: node.name || node.node_id,
        meta: `${connections} connections`,
        value: connections,
        color: nodeTypeColor(node.node_type),
      }
    },
    (node) => ({ name: nodeTypeLabel(node.node_type), color: nodeTypeColor(node.node_type) }),
  )

export const TREEMAP_NOTE =
  'Sized by connections in your visible set. Grouped by node type. Drag to pan, wheel to zoom.'
