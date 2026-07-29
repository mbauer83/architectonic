/**
 * Serialize/deserialize `TracePatternNode`s to the persisted `trace_patterns:` mapping form —
 * the exact mirror of `viewpoint_trace_pattern_serialization.py` / `_parsing.py` so a
 * round-trip through the backend loader is byte-faithful. Structural only: the loader is the
 * single validator (I-G8), so this never rejects — it emits what the loader will re-parse.
 */

import {
  type BranchesNode,
  type DiagnosticEdgeNode,
  type DiagnosticStatus,
  type EdgeDirection,
  type LeafEndpointNode,
  type LeafNode,
  type RealizerRegistry,
  type StoredEdgeNode,
  type TracePatternNode,
  mkDiagnosticEdge,
  mkStoredEdge,
  mkTracePattern,
} from './viewpointTracePattern'

const asRecord = (raw: unknown): Record<string, unknown> => (raw ?? {}) as Record<string, unknown>

/** Stringify an `unknown` that the grammar declares as a string field — never risk an object's
 * `[object Object]` default stringification (mirrors `stringOrNull` in the criteria serializer). */
const str = (v: unknown, fallback = ''): string => (typeof v === 'string' ? v : fallback)

const storedEdgeToMapping = (edge: StoredEdgeNode): Record<string, unknown> => ({
  kind: 'stored-edge',
  connection: edge.connection,
  direction: edge.direction,
  endpoint: { type: edge.endpointType },
})

const diagnosticEdgeToMapping = (edge: DiagnosticEdgeNode): Record<string, unknown> => ({
  kind: 'diagnostic-edge',
  connection: edge.connection,
  direction: edge.direction,
  endpoint: { type: edge.endpointType },
  status: edge.status,
})

const branchesToMapping = (branches: BranchesNode): Record<string, unknown> => {
  if (branches.kind === 'ref') return { ref: branches.ref }
  const out: Record<string, unknown> = {}
  for (const edge of branches.edges) out[edge.label] = storedEdgeToMapping(edge)
  return out
}

const leafEndpointToMapping = (endpoint: LeafEndpointNode): Record<string, unknown> =>
  endpoint.kind === 'registry'
    ? { registry: endpoint.registry }
    : endpoint.entityClass === null
      ? { domain: endpoint.domain }
      : { domain: endpoint.domain, class: endpoint.entityClass }

const leafToMapping = (leaf: LeafNode): Record<string, unknown> =>
  leaf.kind === 'none'
    ? { kind: 'none' }
    : {
        kind: 'derived-reachability',
        connection: leaf.connection,
        traversal: leaf.traversal,
        max_hops: leaf.maxHops,
        endpoint: leafEndpointToMapping(leaf.endpoint),
      }

export const tracePatternToMapping = (pattern: TracePatternNode): Record<string, unknown> => {
  const out: Record<string, unknown> = {
    name: pattern.name,
    kind: 'branch-complete-realization',
    applies_to: [...pattern.appliesTo],
    branches: branchesToMapping(pattern.branches),
  }
  if (pattern.shortcuts.length > 0) out.shortcuts = pattern.shortcuts.map(diagnosticEdgeToMapping)
  out.leaf = leafToMapping(pattern.leaf)
  if (pattern.diagnostic) out.diagnostic = true
  return out
}

const edgeDirectionFromRaw = (raw: unknown): EdgeDirection => (raw === 'outgoing' ? 'outgoing' : 'incoming')

const endpointTypeFromRaw = (raw: unknown): string => str(asRecord(raw).type)

const branchesFromMapping = (raw: unknown): BranchesNode => {
  const rec = asRecord(raw)
  if ('ref' in rec) return { kind: 'ref', ref: str(rec.ref) }
  const edges: StoredEdgeNode[] = Object.entries(rec).map(([label, edge]) => {
    const node = mkStoredEdge(label)
    const e = asRecord(edge)
    node.connection = str(e.connection)
    node.direction = edgeDirectionFromRaw(e.direction)
    node.endpointType = endpointTypeFromRaw(e.endpoint)
    return node
  })
  return { kind: 'inline', edges }
}

const leafEndpointFromMapping = (raw: unknown): LeafEndpointNode => {
  const rec = asRecord(raw)
  if ('registry' in rec) return { kind: 'registry', registry: str(rec.registry) as RealizerRegistry }
  return {
    kind: 'layer',
    domain: str(rec.domain),
    entityClass: rec.class != null ? str(rec.class) : null,
  }
}

const leafFromMapping = (raw: unknown): LeafNode => {
  const rec = asRecord(raw)
  if (rec.kind !== 'derived-reachability') return { kind: 'none' }
  return {
    kind: 'derived-reachability',
    connection: str(rec.connection),
    traversal: 'direct_and_derived',
    maxHops: typeof rec.max_hops === 'number' ? rec.max_hops : 4,
    endpoint: leafEndpointFromMapping(rec.endpoint),
  }
}

export const tracePatternFromMapping = (raw: unknown): TracePatternNode => {
  const rec = asRecord(raw)
  const pattern = mkTracePattern()
  pattern.name = str(rec.name)
  pattern.appliesTo = Array.isArray(rec.applies_to) ? rec.applies_to.map((t) => str(t)) : []
  pattern.branches = branchesFromMapping(rec.branches)
  pattern.shortcuts = Array.isArray(rec.shortcuts)
    ? rec.shortcuts.map((s) => {
        const e = asRecord(s)
        const node = mkDiagnosticEdge()
        node.connection = str(e.connection)
        node.direction = edgeDirectionFromRaw(e.direction)
        node.endpointType = endpointTypeFromRaw(e.endpoint)
        node.status = str(e.status, 'shortcut') as DiagnosticStatus
        return node
      })
    : []
  pattern.leaf = leafFromMapping(rec.leaf)
  pattern.diagnostic = rec.diagnostic === true
  return pattern
}
