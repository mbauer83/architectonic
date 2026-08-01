// Pure helpers for the STPA wizard — unit-testable without a DOM.

import { UCA_GUIDEWORD_SLUGS, canonicalGuideword } from '../lib/ucaGuidewords'

export interface StpaRelation {
  connType: string
  targetType: string
  targetLabel: string
}

export interface StpaStep {
  key: string
  label: string
  /** Assurance node_type created in this step ('' for the review step). */
  nodeType: string
  /** assurance_guidance topic for the step's coaching panel. */
  guidanceTopic: string
  /** Optional outgoing relation this step's nodes should declare (drives completeness). */
  relation?: StpaRelation
}

// STPA flow: Losses → Hazards → Control Structure → UCAs → Constraints → Review.
export const STPA_STEPS: StpaStep[] = [
  { key: 'losses', label: 'Losses', nodeType: 'loss', guidanceTopic: 'stpa-losses' },
  {
    key: 'hazards', label: 'Hazards', nodeType: 'hazard', guidanceTopic: 'stpa-hazards',
    relation: { connType: 'leads-to', targetType: 'loss', targetLabel: 'loss' },
  },
  {
    key: 'control-structure', label: 'Control Structure',
    nodeType: 'control-structure-node', guidanceTopic: 'stpa-control-structure',
  },
  {
    key: 'ucas', label: 'UCAs', nodeType: 'unsafe-control-action', guidanceTopic: 'stpa-ucas',
    relation: { connType: 'leads-to', targetType: 'hazard', targetLabel: 'hazard' },
  },
  {
    key: 'constraints', label: 'Constraints',
    nodeType: 'assurance-constraint', guidanceTopic: 'stpa-constraints',
  },
  { key: 'review', label: 'Review', nodeType: '', guidanceTopic: '' },
]

export const STPA_GUIDEWORDS = UCA_GUIDEWORD_SLUGS
export type StpaGuideword = string

export interface AssuranceNode {
  node_id: string
  node_type: string
  name: string
  uca_type?: string
  binding_status?: string
}

export interface AssuranceEdge {
  source_id: string
  target_id: string
  conn_type: string
}

/** Synthesised UCA name for a (control-action, guideword) cell. */
export function ucaName(controlActionName: string, guideword: StpaGuideword): string {
  return `${controlActionName} — ${guideword}`
}

export interface GridCell {
  guideword: StpaGuideword
  existing: AssuranceNode | null
}

export interface GridRow {
  controlAction: AssuranceNode
  cells: GridCell[]
}

/**
 * Build the UCA guideword grid: one row per control-action, one cell per
 * guideword. A cell is "existing" when a UCA already `concerns` that action with
 * that guideword (matched via the concerns edge + uca_type).
 */
export function buildGuidewordGrid(
  controlActions: AssuranceNode[],
  ucas: AssuranceNode[],
  concernsEdges: AssuranceEdge[],
): GridRow[] {
  const ucaById = new Map(ucas.map((u) => [u.node_id, u]))
  // action_id -> guideword -> uca
  const byAction = new Map<string, Map<string, AssuranceNode>>()
  for (const edge of concernsEdges) {
    if (edge.conn_type !== 'concerns') continue
    const uca = ucaById.get(edge.source_id)
    if (!uca?.uca_type) continue
    if (!byAction.has(edge.target_id)) byAction.set(edge.target_id, new Map())
    // Keyed by the current guideword: a UCA persisted under a legacy one must still show as
    // existing, or the wizard invites the analyst to create a duplicate.
    byAction.get(edge.target_id)!.set(canonicalGuideword(uca.uca_type), uca)
  }
  return controlActions.map((ca) => ({
    controlAction: ca,
    cells: STPA_GUIDEWORDS.map((gw) => ({
      guideword: gw,
      existing: byAction.get(ca.node_id)?.get(gw) ?? null,
    })),
  }))
}

export interface StpaCheck {
  passed: boolean
  gap_count: number
}

export interface StpaCompleteResponse {
  passed: boolean
  checks: Record<string, StpaCheck>
}

export interface StpaCompleteSummary {
  passed: boolean
  failed: { key: string; gapCount: number }[]
}

export function summariseStpaComplete(resp: StpaCompleteResponse): StpaCompleteSummary {
  const failed = Object.entries(resp.checks)
    .filter(([, c]) => !c.passed)
    .map(([key, c]) => ({ key, gapCount: c.gap_count }))
  return { passed: resp.passed, failed }
}

/** Which step keys already have at least one authored node (for the stepper badges). */
export function stepsWithContent(nodes: AssuranceNode[]): Set<string> {
  const present = new Set(nodes.map((n) => n.node_type))
  const keys = new Set<string>()
  for (const step of STPA_STEPS) {
    if (step.nodeType && present.has(step.nodeType)) keys.add(step.key)
  }
  return keys
}

/** Control-structure nodes that still need an architecture binding. */
export function unboundControlNodes(nodes: AssuranceNode[]): AssuranceNode[] {
  return nodes.filter(
    (n) => n.node_type === 'control-structure-node' && n.binding_status === 'unbound-pending',
  )
}

import { assuranceAnalysisCreateRoute, assuranceAnalysisMethodRoute } from '../router/artifactRoutes'

/** Where the wizard goes when its analysis selection changes: that analysis' surface, or the
 * create surface when the selection is cleared. Here rather than in the view because it is a
 * route decision, and this module already holds the wizard's others. */
export const selectionRoute = (analysisId: string | null): string =>
  analysisId ? assuranceAnalysisMethodRoute(analysisId, 'stpa') : assuranceAnalysisCreateRoute('stpa')
