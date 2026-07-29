// Pure helpers for the CAST wizard — unit-testable without a DOM.

export interface CastStep {
  key: string
  label: string
  /** Assurance node_type created in this step ('' for baseline/review steps). */
  nodeType: string
  /** assurance_guidance topic for the step's coaching panel ('' = no panel). */
  guidanceTopic: string
}

// CAST flow: Baseline → Incident → Investigate → Corrective Actions → Review.
export const CAST_STEPS: CastStep[] = [
  { key: 'baseline', label: 'Baseline', nodeType: '', guidanceTopic: 'cast-investigation' },
  { key: 'incident', label: 'Incident', nodeType: 'incident', guidanceTopic: 'cast-investigation' },
  { key: 'investigate', label: 'Investigate', nodeType: 'control-structure-node', guidanceTopic: 'cast-investigation' },
  { key: 'corrective', label: 'Corrective Actions', nodeType: 'corrective-action', guidanceTopic: 'cast-investigation' },
  { key: 'review', label: 'Review', nodeType: '', guidanceTopic: '' },
]

export interface AssuranceNode {
  node_id: string
  node_type: string
  name: string
}

export interface AssuranceEdge {
  source_id: string
  target_id: string
  conn_type: string
}

export interface Baseline {
  baseline_id: string
  created_at?: string
  notes?: string
}

/** Source ids already linked to `targetId` via `connType`. */
export function linkedSourceIds(
  edges: AssuranceEdge[],
  targetId: string,
  connType: string,
): Set<string> {
  return new Set(
    edges.filter((e) => e.target_id === targetId && e.conn_type === connType).map((e) => e.source_id),
  )
}

/** Candidate sources of one type not yet linked to `targetId` via `connType`. */
export function unlinkedSources(
  sources: AssuranceNode[],
  edges: AssuranceEdge[],
  targetId: string,
  connType: string,
): AssuranceNode[] {
  const linked = linkedSourceIds(edges, targetId, connType)
  return sources.filter((s) => !linked.has(s.node_id))
}

/** Targets a `source` node already points to via `connType`. */
export function linkedTargetIds(
  edges: AssuranceEdge[],
  sourceId: string,
  connType: string,
): Set<string> {
  return new Set(
    edges.filter((e) => e.source_id === sourceId && e.conn_type === connType).map((e) => e.target_id),
  )
}

export interface CastCheck {
  passed: boolean
  gap_count: number
  gaps?: { node_id: string; name: string }[]
}

export interface CastCompleteResponse {
  passed: boolean
  checks: Record<string, CastCheck>
  baseline_count?: number
  incident_count?: number
}

export interface CastCompleteSummary {
  passed: boolean
  failed: { key: string; gapCount: number }[]
}

export function summariseCastComplete(resp: CastCompleteResponse): CastCompleteSummary {
  const failed = Object.entries(resp.checks)
    .filter(([, c]) => !c.passed)
    .map(([key, c]) => ({ key, gapCount: c.gap_count }))
  return { passed: resp.passed, failed }
}

/** Node ids flagged as gaps by a named completeness check. */
export function gapNodeIds(resp: CastCompleteResponse | null, checkKey: string): Set<string> {
  const gaps = resp?.checks?.[checkKey]?.gaps ?? []
  return new Set(gaps.map((g) => g.node_id))
}

/** Which step keys already have meaningful content (for the stepper badges). */
export function castStepBadges(nodes: AssuranceNode[], baselineCount: number): Set<string> {
  const keys = new Set<string>()
  if (baselineCount > 0) keys.add('baseline')
  if (nodes.some((n) => n.node_type === 'incident')) keys.add('incident')
  if (nodes.some((n) => n.node_type === 'control-structure-node')) keys.add('investigate')
  if (nodes.some((n) => n.node_type === 'corrective-action')) keys.add('corrective')
  return keys
}
