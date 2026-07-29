import { canonicalGuideword } from '../lib/ucaGuidewords'

export interface AssuranceDiagramNode {
  node_id: string
  node_type: string
  name: string
  uca_type?: string
}

export interface AssuranceDiagramEdge {
  edge_id?: string
  source_id: string
  target_id: string
  conn_type: string
  label?: string
  name?: string
}

/**
 * A drawn edge that stands for a **node** rather than for a connection.
 *
 * A notation may render a node as the arrow between its neighbours instead of as a shape of its
 * own — a STAMP control action is the labelled arrow from a controller to what it controls. The
 * node still carries everything worth opening (its status, TLP, architecture binding, and the
 * unsafe control actions enumerated against it), so the arrow has to select the node. The backend
 * reports which edge represents which node; the viewer does not need to know the notation.
 */
export interface NodeRepresentingEdge {
  node_id: string
  source_id: string
  target_id: string
}

export interface UcaMatrixRow {
  controlAction: AssuranceDiagramNode
  cells: Record<string, AssuranceDiagramNode[]>
}

export function buildUcaMatrixRows(
  nodes: ReadonlyArray<AssuranceDiagramNode>,
  edges: ReadonlyArray<AssuranceDiagramEdge>,
): UcaMatrixRow[] {
  const actions = nodes.filter((node) => node.node_type === 'control-action')
  const ucas = new Map(
    nodes
      .filter((node) => node.node_type === 'unsafe-control-action')
      .map((node) => [node.node_id, node]),
  )
  const actionById = new Map(actions.map((node) => [node.node_id, node]))
  const cellsByAction = new Map<string, Record<string, AssuranceDiagramNode[]>>()
  for (const edge of edges) {
    if (edge.conn_type !== 'concerns') continue
    const uca = ucas.get(edge.source_id)
    if (!uca || !actionById.has(edge.target_id)) continue
    const cells = cellsByAction.get(edge.target_id) ?? {}
    // A legacy guideword is folded into its current column, so a store that has not been
    // migrated yet still groups correctly instead of growing a stray column.
    const key = canonicalGuideword(uca.uca_type) || 'unspecified'
    ;(cells[key] ??= []).push(uca)
    cellsByAction.set(edge.target_id, cells)
  }
  return actions.map((controlAction) => ({
    controlAction,
    cells: cellsByAction.get(controlAction.node_id) ?? {},
  }))
}
