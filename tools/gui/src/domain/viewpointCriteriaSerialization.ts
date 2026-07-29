/**
 * Builder tree <-> canonical wire mapping conversion — the exact counterpart of
 * `src/domain/viewpoints/viewpoint_criteria_serialization.py` / `viewpoint_criteria_parsing.py`: same
 * omit-defaults-on-write rules, same discriminated `kind` dispatch. `parse ∘ serialize`
 * must be the identity on every valid tree, verified by `viewpointCriteriaSerialization.test.ts`.
 */

import {
  type Comparator,
  type ConditionNode, type Conjunction,
  type ConnectionSelectionNode,
  type CriteriaNode,
  type ExecutableQueryNode,
  type GroupKind,
  type GroupNode,
  type IncidentDirection,
  type IncidentTraversal,
  type IncidentNode,
  type NeighborInclusionNode,
  type Quantifier,
  type RelationshipTraversal,
  type ValueRef,
  bindingValue,
  endpointValue,
  literalValue,
  mkConnectionSelection,
  mkGroup,
  mkQuery,
  nextNodeId,
  parameterValue,
  selfValue,
} from './viewpointCriteria'
import type { AggregateKind, AttributeTypeTables } from './viewpointBindings'
import {
  bindingFromMapping,
  bindingToMapping,
  derivedAttributeFromMapping,
  derivedAttributeToMapping,
  parameterFromMapping,
  parameterToMapping,
} from './viewpointBindingsSerialization'
import { tracePatternFromMapping, tracePatternToMapping } from './viewpointTracePatternSerialization'

/** See `viewpointDefinitionSerialization.ts`'s `stringOr` for why this exists: `String()`
 * on an `unknown` narrowed by `!= null` trips `@typescript-eslint/no-base-to-string`. */
const stringOrNull = (v: unknown): string | null =>
  typeof v === 'string' || typeof v === 'number' ? String(v) : null

// ── to mapping ────────────────────────────────────────────────────────────────

export const valueRefToRaw = (value: ValueRef): unknown => {
  if (value.kind === 'literal') return value.literal
  if (value.kind === 'parameter') return { from: 'parameter', name: value.parameter }
  if (value.kind === 'binding') {
    const result: Record<string, unknown> = { from: 'binding', name: value.binding }
    if (value.project !== null) result.project = value.project
    if (value.aggregate !== null) result.aggregate = value.aggregate
    if (value.quantifier !== null) result.quantifier = value.quantifier
    return result
  }
  const from = value.kind === 'self' ? 'self' : value.kind
  return { from, attribute: value.attribute }
}

/** Mirrors `ValueRef()`'s default (`kind="literal", literal=None`) — the wire shape a
 * condition's absent `value` key parses to (`_value_ref_from_raw(raw.get("value"))` with
 * no key present). Distinct from `mkCondition`'s UI-ergonomic starting value (`''`, a
 * blank text field) — this is only the *parse* default used for the omit-on-write check. */
const isUnsetValue = (value: ValueRef): boolean => value.kind === 'literal' && value.literal === null

const conditionToMapping = (node: ConditionNode): Record<string, unknown> => {
  const result: Record<string, unknown> = { kind: 'condition', attribute: node.attribute, comparator: node.comparator }
  if (!isUnsetValue(node.value)) result.value = valueRefToRaw(node.value)
  if (node.negate) result.negate = true
  return result
}

const incidentToMapping = (node: IncidentNode): Record<string, unknown> => {
  const result: Record<string, unknown> = { kind: 'incident' }
  if (node.direction !== 'either') result.direction = node.direction
  if (node.connectionCriteria !== null) result.connection_criteria = groupToMapping(node.connectionCriteria)
  if (node.endpointCriteria !== null) result.endpoint_criteria = groupToMapping(node.endpointCriteria)
  if (node.negate) result.negate = true
  // Always written, even at the default — a predicate's traversal is load-bearing
  // semantics, and dropping it on re-save would silently rewrite a loaded definition.
  result.traversal = node.traversal
  return result
}

const criteriaNodeToMapping = (node: CriteriaNode): Record<string, unknown> => {
  if (node.kind === 'condition') return conditionToMapping(node)
  if (node.kind === 'incident') return incidentToMapping(node)
  return groupToMapping(node)
}

export const groupToMapping = (group: GroupNode): Record<string, unknown> => {
  const result: Record<string, unknown> = {
    kind: 'group', conjunction: group.conjunction, children: group.children.map(criteriaNodeToMapping),
  }
  if (group.negate) result.negate = true
  return result
}

export const neighborInclusionToMapping = (inclusion: NeighborInclusionNode): Record<string, unknown> => {
  const result: Record<string, unknown> = {}
  if (inclusion.direction !== 'either') result.direction = inclusion.direction
  if (inclusion.connectionCriteria !== null) result.connection_criteria = groupToMapping(inclusion.connectionCriteria)
  if (inclusion.neighborCriteria !== null) result.neighbor_criteria = groupToMapping(inclusion.neighborCriteria)
  if (inclusion.traversal !== 'direct') result.traversal = inclusion.traversal
  if (inclusion.includePotential) result.include_potential = true
  if (inclusion.maxHops !== null) result.max_hops = inclusion.maxHops
  return result
}

const isDefaultConnectionGroup = (group: GroupNode): boolean =>
  group.conjunction === 'and' && !group.negate && group.children.length === 0

export const connectionSelectionToMapping = (selection: ConnectionSelectionNode): Record<string, unknown> => {
  const result: Record<string, unknown> = {}
  if (!selection.enabled) result.enabled = false
  if (!isDefaultConnectionGroup(selection.criteria)) result.criteria = groupToMapping(selection.criteria)
  if (selection.traversal !== 'direct') result.traversal = selection.traversal
  if (selection.includePotential) result.include_potential = true
  if (selection.maxHops !== null) result.max_hops = selection.maxHops
  return result
}

// ── from mapping ──────────────────────────────────────────────────────────────

export const valueRefFromRaw = (raw: unknown): ValueRef => {
  if (raw !== null && typeof raw === 'object' && 'from' in (raw as Record<string, unknown>)) {
    const rec = raw as Record<string, unknown>
    const from = String(rec.from)
    if (from === 'parameter') return parameterValue(String(rec.name))
    if (from === 'binding') {
      return bindingValue(String(rec.name), {
        project: stringOrNull(rec.project),
        aggregate: rec.aggregate != null ? (stringOrNull(rec.aggregate) as AggregateKind) : null,
        quantifier: rec.quantifier != null ? (stringOrNull(rec.quantifier) as Quantifier) : null,
      })
    }
    const attribute = String(rec.attribute)
    return from === 'self' ? selfValue(attribute) : endpointValue(from as 'source' | 'target', attribute)
  }
  return literalValue(raw ?? null)
}

const asRecord = (raw: unknown): Record<string, unknown> => raw as Record<string, unknown>

const conditionFromMapping = (raw: Record<string, unknown>): ConditionNode => ({
  kind: 'condition', id: nextNodeId(),
  attribute: String(raw.attribute), comparator: raw.comparator as Comparator,
  value: valueRefFromRaw(raw.value), negate: Boolean(raw.negate ?? false),
})

const incidentFromMapping = (raw: Record<string, unknown>): IncidentNode => ({
  kind: 'incident', id: nextNodeId(),
  direction: (raw.direction as IncidentDirection) ?? 'either',
  negate: Boolean(raw.negate ?? false),
  traversal: (raw.traversal as IncidentTraversal) ?? 'direct',
  connectionCriteria: raw.connection_criteria != null ? groupFromMapping(asRecord(raw.connection_criteria), 'connection') : null,
  endpointCriteria: raw.endpoint_criteria != null ? groupFromMapping(asRecord(raw.endpoint_criteria), 'entity') : null,
})

const criteriaNodeFromMapping = (raw: Record<string, unknown>, groupKind: GroupKind): CriteriaNode => {
  if (raw.kind === 'condition') return conditionFromMapping(raw)
  if (raw.kind === 'incident' && groupKind === 'entity') return incidentFromMapping(raw)
  if (raw.kind === 'group') return groupFromMapping(raw, groupKind)
  throw new Error(`unknown criteria node kind ${String(raw.kind)}`)
}

export const groupFromMapping = (raw: Record<string, unknown>, groupKind: GroupKind): GroupNode => {
  const children = Array.isArray(raw.children) ? raw.children : []
  const node = mkGroup(groupKind, (raw.conjunction as Conjunction) ?? 'and')
  node.negate = Boolean(raw.negate ?? false)
  node.children = children.map((child) => criteriaNodeFromMapping(asRecord(child), groupKind))
  return node
}

export const neighborInclusionFromMapping = (raw: Record<string, unknown>): NeighborInclusionNode => ({
  id: nextNodeId(),
  direction: (raw.direction as IncidentDirection) ?? 'either',
  connectionCriteria: raw.connection_criteria != null ? groupFromMapping(asRecord(raw.connection_criteria), 'connection') : null,
  neighborCriteria: raw.neighbor_criteria != null ? groupFromMapping(asRecord(raw.neighbor_criteria), 'entity') : null,
  traversal: (raw.traversal as RelationshipTraversal) ?? 'direct',
  includePotential: Boolean(raw.include_potential ?? false),
  maxHops: typeof raw.max_hops === 'number' ? raw.max_hops : null,
})

export const connectionSelectionFromMapping = (raw: unknown): ConnectionSelectionNode => {
  if (raw == null) return mkConnectionSelection()
  const rec = asRecord(raw)
  return {
    enabled: Boolean(rec.enabled ?? true),
    criteria: rec.criteria != null ? groupFromMapping(asRecord(rec.criteria), 'connection') : mkGroup('connection'),
    traversal: (rec.traversal as RelationshipTraversal) ?? 'direct',
    includePotential: Boolean(rec.include_potential ?? false),
    maxHops: typeof rec.max_hops === 'number' ? rec.max_hops : null,
  }
}

/** `attributeTypes` defaults to empty tables — safe whenever no binding actually `project`s
 * an attribute, since it is only consulted for that. Callers authoring bindings with
 * `project` should pass the criteria catalog's real `entity_attribute_types`/
 * `connection_attribute_types` for an accurate declared `result_type`. */
export const queryToMapping = (
  query: ExecutableQueryNode,
  attributeTypes: AttributeTypeTables = { entity: {}, connection: {} },
): Record<string, unknown> => {
  const result: Record<string, unknown> = {
    query_schema: query.querySchema,
    entity_criteria: groupToMapping(query.entityCriteria),
  }
  if (query.includeConnected.length > 0) {
    result.include_connected = query.includeConnected.map(neighborInclusionToMapping)
  }
  const connections = connectionSelectionToMapping(query.connections)
  if (Object.keys(connections).length > 0) result.connections = connections
  if (query.bindings.length > 0) {
    result.bindings = query.bindings.map((b) => bindingToMapping(b, query.bindings, attributeTypes))
  }
  if (query.parameters.length > 0) result.parameters = query.parameters.map(parameterToMapping)
  if (query.derived.length > 0) result.derived = query.derived.map(derivedAttributeToMapping)
  if (query.tracePatterns.length > 0) result.trace_patterns = query.tracePatterns.map(tracePatternToMapping)
  return result
}

export const queryFromMapping = (raw: unknown): ExecutableQueryNode => {
  const query = mkQuery()
  if (raw == null) return query
  const rec = asRecord(raw)
  query.entityCriteria = rec.entity_criteria != null ? groupFromMapping(asRecord(rec.entity_criteria), 'entity') : mkGroup('entity')
  query.includeConnected = Array.isArray(rec.include_connected)
    ? rec.include_connected.map((i) => neighborInclusionFromMapping(asRecord(i)))
    : []
  query.connections = connectionSelectionFromMapping(rec.connections)
  query.bindings = Array.isArray(rec.bindings) ? rec.bindings.map(bindingFromMapping) : []
  query.parameters = Array.isArray(rec.parameters) ? rec.parameters.map(parameterFromMapping) : []
  query.derived = Array.isArray(rec.derived) ? rec.derived.map(derivedAttributeFromMapping) : []
  query.tracePatterns = Array.isArray(rec.trace_patterns) ? rec.trace_patterns.map(tracePatternFromMapping) : []
  return query
}
