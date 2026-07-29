/**
 * Pure, Vue-free helpers for the trace-pattern authoring editor: immutable-ish array mutations
 * (the panel owns the array, these return new arrays so change detection is trivial) and the
 * sample preview. The preview reuses the SAME `TraceTable` projection the result table uses
 * (I-G5: one serializer), so an author sees exactly the two cell shapes a real execution
 * produces — one authoritative verdict cell and one diagnostic observation cell.
 */
import type { TraceTable } from '../../domain/schemas/viewpoints'
import {
  type DiagnosticEdgeNode,
  type LeafNode,
  type RealizerRegistry,
  type StoredEdgeNode,
  type TracePatternNode,
  VALID_REALIZER_REGISTRIES,
  mkDiagnosticEdge,
  mkStoredEdge,
} from '../../domain/viewpointTracePattern'

type DerivedLeaf = Extract<LeafNode, { kind: 'derived-reachability' }>

/** Patch a pattern's derived-reachability leaf; a no-op if the leaf is `none` (the template only
 * exposes these controls when the leaf is derived, so the guard is defensive). */
const withDerivedLeaf = (pattern: TracePatternNode, patch: Partial<DerivedLeaf>): TracePatternNode =>
  pattern.leaf.kind === 'derived-reachability'
    ? { ...pattern, leaf: { ...pattern.leaf, ...patch } }
    : pattern

export const setLeafConnection = (pattern: TracePatternNode, connection: string): TracePatternNode =>
  withDerivedLeaf(pattern, { connection })

export const setLeafMaxHops = (pattern: TracePatternNode, maxHops: number): TracePatternNode =>
  withDerivedLeaf(pattern, { maxHops })

export const setLeafRegistry = (pattern: TracePatternNode, registry: RealizerRegistry): TracePatternNode =>
  withDerivedLeaf(pattern, { endpoint: { kind: 'registry', registry } })

export const setLeafLayerDomain = (pattern: TracePatternNode, domain: string): TracePatternNode =>
  withDerivedLeaf(pattern, { endpoint: { kind: 'layer', domain, entityClass: null } })

/** Switch the leaf target between the realizer registry and layer membership. */
export const setLeafEndpointKind = (
  pattern: TracePatternNode, kind: 'registry' | 'layer', firstDomain: string,
): TracePatternNode =>
  withDerivedLeaf(pattern, {
    endpoint: kind === 'registry'
      ? { kind: 'registry', registry: VALID_REALIZER_REGISTRIES[0] }
      : { kind: 'layer', domain: firstDomain, entityClass: null },
  })

export const addPattern = (patterns: readonly TracePatternNode[], pattern: TracePatternNode): TracePatternNode[] =>
  [...patterns, pattern]

export const removeAt = <T>(items: readonly T[], index: number): T[] => items.filter((_, i) => i !== index)

export const replaceAt = <T>(items: readonly T[], index: number, next: T): T[] =>
  items.map((item, i) => (i === index ? next : item))

/** Toggle a value in a string set (used for `applies_to` type membership checkboxes). */
export const toggleMember = (values: readonly string[], value: string): string[] =>
  values.includes(value) ? values.filter((v) => v !== value) : [...values, value]

/** Switch a pattern's branches between inline edges and a {ref}, preserving nothing across the
 * boundary (the two shapes are disjoint) — a fresh inline edge list or an empty ref. */
export const setBranchesInline = (pattern: TracePatternNode): TracePatternNode => ({
  ...pattern,
  branches: pattern.branches.kind === 'inline' ? pattern.branches : { kind: 'inline', edges: [mkStoredEdge()] },
})

export const setBranchesRef = (pattern: TracePatternNode, ref = ''): TracePatternNode => ({
  ...pattern,
  branches: { kind: 'ref', ref },
})

export const addBranchEdge = (pattern: TracePatternNode): TracePatternNode =>
  pattern.branches.kind === 'inline'
    ? { ...pattern, branches: { kind: 'inline', edges: [...pattern.branches.edges, mkStoredEdge()] } }
    : pattern

export const updateBranchEdge = (pattern: TracePatternNode, index: number, edge: StoredEdgeNode): TracePatternNode =>
  pattern.branches.kind === 'inline'
    ? { ...pattern, branches: { kind: 'inline', edges: replaceAt(pattern.branches.edges, index, edge) } }
    : pattern

export const removeBranchEdge = (pattern: TracePatternNode, index: number): TracePatternNode =>
  pattern.branches.kind === 'inline'
    ? { ...pattern, branches: { kind: 'inline', edges: removeAt(pattern.branches.edges, index) } }
    : pattern

export const addShortcut = (pattern: TracePatternNode): TracePatternNode =>
  ({ ...pattern, shortcuts: [...pattern.shortcuts, mkDiagnosticEdge()] })

export const updateShortcut = (pattern: TracePatternNode, index: number, edge: DiagnosticEdgeNode): TracePatternNode =>
  ({ ...pattern, shortcuts: replaceAt(pattern.shortcuts, index, edge) })

export const removeShortcut = (pattern: TracePatternNode, index: number): TracePatternNode =>
  ({ ...pattern, shortcuts: removeAt(pattern.shortcuts, index) })

/** Toggle the derived-reachability leaf on/off. The "on" default is a registry realizer leaf,
 * the only leaf the authoritative overall column uses; layer leaves are the diagnostic columns. */
export const setLeafNone = (pattern: TracePatternNode): TracePatternNode => ({ ...pattern, leaf: { kind: 'none' } })

export const setLeafDerived = (pattern: TracePatternNode): TracePatternNode =>
  pattern.leaf.kind === 'derived-reachability'
    ? pattern
    : {
        ...pattern,
        leaf: {
          kind: 'derived-reachability',
          connection: 'archimate-realization',
          traversal: 'direct_and_derived',
          maxHops: 4,
          endpoint: { kind: 'registry', registry: 'permitted-realizers-of-requirement' },
        },
      }

/** Count the edges a pattern declares (branch + shortcut) for the structural cap warning. A
 * {ref} counts as 0 here — the loader measures caps AFTER expansion, so the GUI shows the
 * inline declaration count and defers the expanded cap to the loader (single validator). */
export const declaredEdgeCount = (pattern: TracePatternNode): number =>
  (pattern.branches.kind === 'inline' ? pattern.branches.edges.length : 0) + pattern.shortcuts.length

/**
 * A synthetic one-row table showing the two cell shapes for a sample entity: an authoritative
 * pattern reporting a gap (2 of 3 branches covered, one missing requirement) and a diagnostic
 * pattern reporting `none_observed`. Rendering this through `ViewpointTraceTable` proves the
 * author which columns are verdicts and which are observations before any real execution.
 */
export const samplePreviewTable = (): TraceTable => ({
  rows: [
    {
      entity_id: 'GOL@sample',
      entity_type: 'goal',
      name: 'Sample goal',
      tier: 'engagement',
      verdict: 'gap',
      pattern_results: [
        [
          'motivation',
          {
            role: 'authoritative',
            verdict: 'gap',
            status_code: 'incomplete_branch',
            coverage: { covered: 2, applicable: 3 },
            incomplete_branch_count: 1,
            failing_obligations: [{ kind: 'missing-requirement', root_id: 'GOL@sample', outcome_id: 'OUT@sample' }],
            failing_overflow: 0,
            last_satisfied_ids: [],
            missing_expected: ['requirement'],
            shortcut: false,
            diagnostic_code: null,
          },
        ],
        [
          'behavior_coverage',
          {
            role: 'diagnostic',
            observation: 'none_observed',
            last_satisfied_ids: [],
          },
        ],
      ],
    },
  ],
  total_rows: 1,
  returned_rows: 1,
  truncated: false,
  derived_truncated: false,
})
