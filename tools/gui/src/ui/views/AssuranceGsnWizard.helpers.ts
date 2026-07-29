export const GSN_STEPS = [
  { key: 'draft', label: 'Draft' },
  { key: 'destination', label: 'Destination' },
  { key: 'preview', label: 'Preview / Publish' },
  { key: 'bindings', label: 'Bindings' },
  { key: 'completeness', label: 'Completeness' },
] as const

export interface GsnNode {
  node_id: string
  name: string
  gsn_type: string
  source_assurance_ids?: string[]
}

export interface GsnDiagramEntities {
  nodes: GsnNode[]
  edges: { source_id: string; target_id: string; conn_type: string }[]
}

export interface GsnDraftResponse {
  diagram_entities: GsnDiagramEntities
  effective_tlp: string
  publishable: boolean
  draft: {
    gaps: {
      constraints_without_evidence: { node_id: string; name: string }[]
      hazards_without_constraints: { node_id: string; name: string }[]
    }
  }
}

export interface CompletenessResponse {
  passed: boolean
  checks: Record<string, { passed: boolean; gap_count: number }>
}

export function sourceBindings(entities: GsnDiagramEntities) {
  return entities.nodes.flatMap((node) =>
    (node.source_assurance_ids ?? []).map((assuranceNodeId) => ({
      assurance_node_id: assuranceNodeId,
      gsn_node_id: node.node_id,
    })),
  )
}

export function completenessFailures(result: CompletenessResponse | null) {
  if (!result) return []
  return Object.entries(result.checks)
    .filter(([, check]) => !check.passed)
    .map(([key, check]) => ({ key, gapCount: check.gap_count }))
}

export function publicationBody(
  analysisId: string,
  diagramId: string,
  entities: GsnDiagramEntities,
) {
  return {
    analysis_id: analysisId,
    diagram_id: diagramId,
    source_bindings: sourceBindings(entities),
  }
}
