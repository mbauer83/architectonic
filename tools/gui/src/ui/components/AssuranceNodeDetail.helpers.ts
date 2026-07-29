/**
 * Pure helpers for AssuranceNodeDetail: edge grouping and endpoint display.
 * Endpoint names come from the server-enriched payload (the exposure policy has
 * already omitted anything not visible); the id fallback only covers responses
 * from older backends, never hidden endpoints.
 */

export interface AssuranceEdge {
  edge_id?: string
  source_id: string
  target_id: string
  conn_type: string
  label?: string
  source_name?: string
  source_type?: string
  target_name?: string
  target_type?: string
}

export function groupByType(edges: AssuranceEdge[]): Record<string, AssuranceEdge[]> {
  const groups: Record<string, AssuranceEdge[]> = {}
  for (const edge of edges) {
    if (!groups[edge.conn_type]) groups[edge.conn_type] = []
    groups[edge.conn_type].push(edge)
  }
  return groups
}

export function endpointLabel(edge: AssuranceEdge, end: 'source' | 'target'): string {
  return (end === 'source' ? edge.source_name : edge.target_name)
    || (end === 'source' ? edge.source_id : edge.target_id)
}

export function nodeBrowsePath(nodeId: string): { path: string; query: { node_id: string } } {
  return { path: '/assurance', query: { node_id: nodeId } }
}
