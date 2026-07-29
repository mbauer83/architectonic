/**
 * Maps a `ViewpointValidationIssue.path` (a JSON-pointer-style path like
 * `/query/entity_criteria/children/0/attribute`, built by `f"{path}/entity_criteria"`-style
 * chains in `src/domain/viewpoints/viewpoint_validation.py`/`viewpoint_criteria_validation.py`) onto
 * the builder node it names, so the management view highlights the exact widget that
 * produced a save-time validation rejection instead of a flat error list.
 *
 * Walks the draft the issue was generated from, segment by segment, dispatching on the
 * STRUCTURAL SHAPE of the current cursor (draft / query / presentation / connection
 * selection / neighbor inclusion / style rule / criteria node) rather than a string-keyed
 * name translation table — each shape only exposes the wire segment names that are
 * actually meaningful for it. A trailing leaf segment (`attribute`/`comparator`/`value`/
 * `slug`/`version`/...) has no builder node of its own; resolution stops at the deepest
 * node reached and that is what a widget highlights.
 */

import type { CriteriaNode, ConnectionSelectionNode, ExecutableQueryNode, GroupNode, NeighborInclusionNode } from './viewpointCriteria'
import type { PresentationNode, StyleRuleNode } from './viewpointPresentation'
import type { ViewpointDefinitionDraft } from './viewpointDefinitionDraft'
import type { DerivedAttributeNode, QueryBindingNode, QueryParameterNode } from './viewpointBindings'
import type { TracePatternNode } from './viewpointTracePattern'

type Cursor =
  | ViewpointDefinitionDraft
  | ExecutableQueryNode
  | PresentationNode
  | ConnectionSelectionNode
  | NeighborInclusionNode
  | StyleRuleNode
  | CriteriaNode
  | QueryBindingNode
  | QueryParameterNode
  | DerivedAttributeNode
  | TracePatternNode
  | readonly CriteriaNode[]
  | readonly NeighborInclusionNode[]
  | readonly StyleRuleNode[]
  | readonly QueryBindingNode[]
  | readonly QueryParameterNode[]
  | readonly DerivedAttributeNode[]
  | readonly TracePatternNode[]
  | GroupNode
  | undefined

const isDraft = (v: object): v is ViewpointDefinitionDraft => 'scope' in v && 'query' in v && 'presentation' in v
const isQuery = (v: object): v is ExecutableQueryNode => 'entityCriteria' in v
const isConnectionSelection = (v: object): v is ConnectionSelectionNode => 'enabled' in v && 'criteria' in v
const isNeighborInclusion = (v: object): v is NeighborInclusionNode => 'neighborCriteria' in v
const isPresentation = (v: object): v is PresentationNode => 'stylingRules' in v
const isStyleRule = (v: object): v is StyleRuleNode => 'matchCriteria' in v
const isCriteriaNode = (v: object): v is CriteriaNode => 'kind' in v
const isQueryBinding = (v: object): v is QueryBindingNode => 'select' in v && 'tupleOf' in v
const isDerivedAttribute = (v: object): v is DerivedAttributeNode => 'ofHead' in v

const step = (cursor: Cursor, segment: string): Cursor => {
  if (cursor == null) return undefined
  if (Array.isArray(cursor)) {
    return /^\d+$/.test(segment) ? (cursor[Number(segment)] as Cursor) : undefined
  }
  if (isDraft(cursor)) {
    if (segment === 'query') return cursor.query ?? undefined
    if (segment === 'presentation') return cursor.presentation ?? undefined
    return undefined // scope/slug/version/name/... are leaves with no builder node
  }
  if (isQuery(cursor)) {
    if (segment === 'entity_criteria') return cursor.entityCriteria
    if (segment === 'include_connected') return cursor.includeConnected
    if (segment === 'connections') return cursor.connections
    if (segment === 'bindings') return cursor.bindings
    if (segment === 'parameters') return cursor.parameters
    if (segment === 'derived') return cursor.derived
    if (segment === 'trace_patterns') return cursor.tracePatterns
    return undefined
  }
  if (isConnectionSelection(cursor)) {
    return segment === 'criteria' ? cursor.criteria : undefined
  }
  if (isNeighborInclusion(cursor)) {
    if (segment === 'connection_criteria') return cursor.connectionCriteria ?? undefined
    if (segment === 'neighbor_criteria') return cursor.neighborCriteria ?? undefined
    return undefined
  }
  if (isPresentation(cursor)) {
    if (segment === 'styling_rules') return cursor.stylingRules
    if (segment === 'row_criteria') return cursor.rowCriteria ?? undefined
    if (segment === 'column_criteria') return cursor.columnCriteria ?? undefined
    return undefined
  }
  if (isStyleRule(cursor)) {
    return segment === 'match_criteria' ? (cursor.matchCriteria ?? undefined) : undefined
  }
  if (isCriteriaNode(cursor)) {
    if (cursor.kind === 'group') return segment === 'children' ? cursor.children : undefined
    if (cursor.kind === 'incident') {
      if (segment === 'connection_criteria') return cursor.connectionCriteria ?? undefined
      if (segment === 'endpoint_criteria') return cursor.endpointCriteria ?? undefined
    }
    return undefined
  }
  if (isQueryBinding(cursor)) {
    return segment === 'criteria' ? cursor.criteria : undefined
  }
  if (isDerivedAttribute(cursor)) {
    if (segment === 'connection_criteria') return cursor.connectionCriteria ?? undefined
    if (segment === 'endpoint_criteria') return cursor.endpointCriteria ?? undefined
    return undefined
  }
  return undefined
}

const nodeIdOf = (cursor: Cursor): string | null =>
  cursor != null && !Array.isArray(cursor) && 'id' in cursor ? cursor.id : null

/** Returns the id of the deepest builder node `path` resolves to, or `null` if it names a
 * plain field with no builder-tree node (e.g. `/slug`, `/version`, a bare `/scope`). */
export const resolveIssuePathNodeId = (path: string, draft: ViewpointDefinitionDraft): string | null => {
  let cursor: Cursor = draft
  let lastNodeId: string | null = null
  for (const segment of path.split('/').filter((s) => s.length > 0)) {
    cursor = step(cursor, segment)
    if (cursor === undefined) break
    const id = nodeIdOf(cursor)
    if (id !== null) lastNodeId = id
  }
  return lastNodeId
}
