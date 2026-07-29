/**
 * Pure helpers for the assurance graph exploration view: typed outcomes for the
 * neighbors fetch (including the locked store collapsing the whole panel —
 * nothing stays on screen and nothing new is fetched), payload normalization
 * into generic canvas nodes/edges, node-type coloring, and the truncation
 * notice for partial (size-budget) results, and the assurance-owned band placement the
 * generic cluster layout is driven by.
 */
import type { BandPlacement } from '../composables/useForceGraphLayout'

export interface AssuranceNeighborNode {
  node_id: string
  name: string
  node_type: string
  hop: number
  is_root: boolean
}

export interface AssuranceNeighborEdge {
  edge_id?: string
  source_id: string
  target_id: string
  conn_type: string
  hop: number
  direction: string
}

export interface AssuranceNeighborsResponse {
  root_id: string
  nodes: AssuranceNeighborNode[]
  edges: AssuranceNeighborEdge[]
  truncated: boolean
  frontier_node_ids: string[]
  visibility_limited: boolean
}

export type NeighborsOutcome =
  | { kind: 'graph'; response: AssuranceNeighborsResponse }
  | { kind: 'locked' }
  | { kind: 'not_found' }
  | { kind: 'retryable'; message: string }
  | { kind: 'error'; message: string }

export const outcomeForResponse = (status: number, body: unknown): NeighborsOutcome => {
  if (status === 200) return { kind: 'graph', response: body as AssuranceNeighborsResponse }
  if (status === 423) return { kind: 'locked' }
  if (status === 404) return { kind: 'not_found' }
  if (status === 503) {
    const message = (body as { message?: string } | null)?.message
      ?? 'The traversal ran past its time budget — retry.'
    return { kind: 'retryable', message }
  }
  return { kind: 'error', message: `Neighbor request failed (${status})` }
}

export interface AssuranceGraphPanelState {
  selectedNodeId: string | null
  lockedMessage: string | null
  errorMessage: string | null
  retryable: boolean
  truncationNotice: string | null
}

export const emptyPanelState = (): AssuranceGraphPanelState => ({
  selectedNodeId: null,
  lockedMessage: null,
  errorMessage: null,
  retryable: false,
  truncationNotice: null,
})

/** Next panel state for a fetch outcome. A locked store collapses everything:
 * selection, notices, and (via `clearsGraph`) the rendered graph itself — the
 * view must fetch nothing further until unlocked. */
export const panelStateForOutcome = (
  outcome: NeighborsOutcome,
  prev: AssuranceGraphPanelState,
): AssuranceGraphPanelState => {
  switch (outcome.kind) {
    case 'graph':
      return {
        ...prev,
        lockedMessage: null,
        errorMessage: null,
        retryable: false,
        truncationNotice: truncationNotice(outcome.response),
      }
    case 'locked':
      return {
        ...emptyPanelState(),
        lockedMessage: 'The assurance store is locked. Run `arch-assurance unlock` and reload.',
      }
    case 'not_found':
      return { ...prev, errorMessage: 'Node not found.', retryable: false, truncationNotice: null }
    case 'retryable':
      return { ...prev, errorMessage: outcome.message, retryable: true, truncationNotice: null }
    case 'error':
      return { ...prev, errorMessage: outcome.message, retryable: false, truncationNotice: null }
  }
}

/** Whether the on-screen graph must be discarded for this outcome. */
export const clearsGraph = (outcome: NeighborsOutcome): boolean => outcome.kind === 'locked'

export const truncationNotice = (response: AssuranceNeighborsResponse): string | null => {
  if (!response.truncated) return null
  const frontier = response.frontier_node_ids.length
  const suffix = frontier > 0
    ? ` Double-click a boundary node to continue exploring (${frontier} cut short).`
    : ''
  return `Partial result: the size budget was reached.${suffix}`
}

/** Same convention as the architecture explorer: the id prefix (e.g. HAZ, UCA)
 * is the in-shape type label. */
export const nodeTypeLabel = (nodeId: string): string => nodeId.split('@')[0]

const ASSURANCE_TYPE_COLORS: Record<string, string> = {
  loss: '#fca5a5',
  hazard: '#fdba74',
  'unsafe-control-action': '#fcd34d',
  'causal-analysis-component': '#fde68a',
  'loss-scenario': '#d8b4fe',
  'assurance-constraint': '#93c5fd',
  'control-structure-node': '#a5b4fc',
  risk: '#f9a8d4',
  obligation: '#86efac',
  evidence: '#99f6e4',
}

export const assuranceNodeColor = (nodeType: string): string =>
  ASSURANCE_TYPE_COLORS[nodeType] ?? '#d1d5db'

/**
 * The analysis order STPA reasons in, top to bottom.
 *
 * The architecture explorer bands by ontology domain because a layered view means something
 * there: intent above, realization descending. Assurance has its own such ordering and it is
 * not the domain stack — it is the causal chain, from what must not happen down to the
 * mechanisms by which it could. Banding on it makes vertical position answer "how far into
 * the analysis is this?", which is the question a reader of an assurance graph is asking.
 *
 * Owned here, in the assurance module, and injected into the generic layout as
 * `placementOf`. The layout serves every graph surface, so it must not learn this vocabulary
 * any more than it learned the architecture one; `tests/architecture/
 * test_generic_graph_module_boundaries.py` holds that line.
 */
const STPA_CHAIN: readonly string[] = [
  'loss',
  'hazard',
  'assurance-constraint',
  'control-structure-node',
  'unsafe-control-action',
  'causal-analysis-component',
  'loss-scenario',
]

/**
 * Types that sit beside the chain rather than in it.
 *
 * Risk is a way of grading what the chain found, and obligation/evidence are the assurance
 * argument built on top of it. None of the three is a step of the causal analysis, so
 * stacking them would assert a place in a sequence they are not part of — the same reason
 * the architecture view lifts `common` and `implementation` out of its realization stack.
 */
const ASIDE_TYPES: Record<string, 'left' | 'right'> = {
  risk: 'left',
  obligation: 'right',
  evidence: 'right',
}

/** The band side types align with: the middle of the chain, so they sit level with it. */
const MIDDLE_CHAIN_BAND = Math.floor(STPA_CHAIN.length / 2)

/** Band and side for an assurance node type. Unknown types fall to the bottom rather than
 *  being dropped, so a node type this build has not heard of is still placed and visible. */
export const assuranceBandPlacement = (nodeType: string): BandPlacement => {
  const side = ASIDE_TYPES[nodeType] ?? null
  if (side !== null) return { band: MIDDLE_CHAIN_BAND, side }
  const index = STPA_CHAIN.indexOf(nodeType)
  return { band: index === -1 ? Number.MAX_SAFE_INTEGER : index, side: null }
}
