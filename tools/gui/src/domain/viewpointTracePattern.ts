/**
 * Editable model for the `trace_patterns:` block of a viewpoint query — mirrors the closed
 * `branch-complete-realization` grammar in `src/domain/viewpoints/viewpoint_trace_patterns.py` (and its
 * parser/serializer). Every node carries a UI-only `id` for issue-highlight targeting; the id
 * is never serialized. The authoring surface exists so the shipped `motivation-coverage`
 * viewpoint (and any repository-authored trace viewpoint) is fully editable in the GUI with
 * progressive disclosure — the deepest constructs (edges/shortcuts/leaf targets) are the tagged
 * variants below; there are no "steps".
 */

import { nextNodeId } from './viewpointCriteria'

export type EdgeDirection = 'incoming' | 'outgoing'
export type DiagnosticStatus = 'shortcut' | 'ambiguous_link'
export type LeafTraversal = 'direct_and_derived'
export type RealizerRegistry = 'permitted-realizers-of-requirement'

export const VALID_EDGE_DIRECTIONS: readonly EdgeDirection[] = ['incoming', 'outgoing']
export const VALID_DIAGNOSTIC_STATUSES: readonly DiagnosticStatus[] = ['shortcut', 'ambiguous_link']
export const VALID_LEAF_TRAVERSALS: readonly LeafTraversal[] = ['direct_and_derived']
export const VALID_REALIZER_REGISTRIES: readonly RealizerRegistry[] = ['permitted-realizers-of-requirement']

// Structural caps — mirror MAX_* in viewpoint_trace_patterns.py so the GUI cannot author a set
// the loader will reject (I-G8: GUI validation == loader validation).
export const MAX_TRACE_PATTERNS = 8
export const MAX_EDGE_DECLARATIONS = 8
export const MAX_LEAF_HOPS = 4

/** A branch edge: one hop the walk must traverse (both endpoints legitimate). */
export interface StoredEdgeNode {
  id: string
  /** The map key under `branches:` — the edge's label (e.g. `goal_to_outcome`). */
  label: string
  connection: string
  direction: EdgeDirection
  endpointType: string
}

/** A diagnostic edge: a shortcut/ambiguous relation observed but not asserted as realization. */
export interface DiagnosticEdgeNode {
  id: string
  connection: string
  direction: EdgeDirection
  endpointType: string
  status: DiagnosticStatus
}

/** Branches are either declared inline or reference another pattern's branches by name. */
export type BranchesNode =
  | { kind: 'inline'; edges: StoredEdgeNode[] }
  | { kind: 'ref'; ref: string }

export type LeafEndpointNode =
  | { kind: 'registry'; registry: RealizerRegistry }
  | { kind: 'layer'; domain: string; entityClass: string | null }

export type LeafNode =
  | { kind: 'none' }
  | {
      kind: 'derived-reachability'
      connection: string
      traversal: LeafTraversal
      maxHops: number
      endpoint: LeafEndpointNode
    }

export interface TracePatternNode {
  id: string
  name: string
  appliesTo: string[]
  branches: BranchesNode
  shortcuts: DiagnosticEdgeNode[]
  leaf: LeafNode
  /** Diagnostic patterns produce an observation, never a verdict (never a gap). */
  diagnostic: boolean
}

export const mkStoredEdge = (label = ''): StoredEdgeNode => ({
  id: nextNodeId(), label, connection: 'archimate-realization', direction: 'incoming', endpointType: '',
})

export const mkDiagnosticEdge = (): DiagnosticEdgeNode => ({
  id: nextNodeId(), connection: '', direction: 'incoming', endpointType: '', status: 'shortcut',
})

export const mkTracePattern = (): TracePatternNode => ({
  id: nextNodeId(),
  name: '',
  appliesTo: [],
  branches: { kind: 'inline', edges: [] },
  shortcuts: [],
  leaf: { kind: 'none' },
  diagnostic: false,
})
