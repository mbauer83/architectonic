/**
 * `QueryBinding`/`QueryParameter`/`DerivedAttribute` <-> canonical wire mapping conversion
 * — the exact counterpart of `_binding_to_mapping`/`_parameter_to_mapping`/
 * `_derived_to_mapping` in `src/domain/viewpoints/viewpoint_query_serialization.py` /
 * `viewpoint_query_parsing.py`. Mirrors `viewpointCriteriaSerialization.ts`'s omit-defaults
 * conventions; imports `groupToMapping`/`groupFromMapping` from there for each construct's
 * own criteria sub-tree, and is imported back for `queryToMapping`/`queryFromMapping` —
 * safe circularly since every use is inside a function body, never at module top level.
 */

import { bindingGroupKind, derivedOfFromString, derivedOfStringFor, mkDerivedAttribute, mkQueryBinding, mkQueryParameter, resultTypeStringFor } from './viewpointBindings'
import type { AttributeTypeTables, DerivedAttributeNode, ParameterValueType, QueryBindingNode, QueryParameterNode } from './viewpointBindings'
import type { GroupKind, IncidentDirection } from './viewpointCriteria'
import { groupFromMapping, groupToMapping } from './viewpointCriteriaSerialization'

const asRecord = (raw: unknown): Record<string, unknown> => raw as Record<string, unknown>

/** See `viewpointDefinitionSerialization.ts`'s `stringOr` for why this exists: `String()`
 * on an `unknown` that might be an object trips `@typescript-eslint/no-base-to-string`. */
const stringOr = (v: unknown, fallback: string): string =>
  typeof v === 'string' || typeof v === 'number' ? String(v) : fallback
const stringOrNull = (v: unknown): string | null =>
  typeof v === 'string' || typeof v === 'number' ? String(v) : null

// ── bindings ──────────────────────────────────────────────────────────────────

export const bindingToMapping = (binding: QueryBindingNode, allBindings: readonly QueryBindingNode[], attributeTypes: AttributeTypeTables): Record<string, unknown> => {
  const result: Record<string, unknown> = {
    name: binding.name,
    result_type: resultTypeStringFor(binding, allBindings, attributeTypes),
  }
  if (binding.mode === 'tuple') {
    result.tuple = [...binding.tupleOf]
    if (binding.includeInResult) result.include_in_result = true
    return result
  }
  result.select = binding.select
  result.criteria = groupToMapping(binding.criteria)
  if (binding.project !== null) result.project = binding.project
  if (binding.aggregate !== null) result.aggregate = binding.aggregate
  if (binding.includeInResult) result.include_in_result = true
  return result
}

export const bindingFromMapping = (raw: unknown): QueryBindingNode => {
  const rec = asRecord(raw)
  const node = mkQueryBinding()
  node.name = stringOr(rec.name, '')
  const tupleOf = rec.tuple
  if (Array.isArray(tupleOf) && tupleOf.length > 0) {
    node.mode = 'tuple'
    node.tupleOf = tupleOf.map((v) => stringOr(v, ''))
  } else {
    node.mode = 'select'
    node.select = rec.select === 'connections' ? 'connections' : 'entities'
    const groupKind: GroupKind = bindingGroupKind(node.select)
    node.criteria = rec.criteria != null ? groupFromMapping(asRecord(rec.criteria), groupKind) : node.criteria
    node.project = stringOrNull(rec.project)
    node.aggregate = rec.aggregate != null ? (stringOr(rec.aggregate, '') as QueryBindingNode['aggregate']) : null
    // Aggregation is only legal over a set source ("aggregate over instance/optional is a
    // static error") — so an aggregated binding's cardinality was always `set`, regardless
    // of what its (collapsed-to-scalar) `result_type` string looks like.
    node.cardinality = node.aggregate !== null ? 'set' : cardinalityFromResultType(stringOr(rec.result_type, ''))
  }
  node.includeInResult = Boolean(rec.include_in_result ?? false)
  return node
}

/** Recovers `instance`/`optional`/`set` from a saved `result_type` string — `entity[…]`/
 * a bare scalar is `instance`, `optional[…]` is `optional`, `entities[…]`/`connections[…]`/
 * `list[…]` (the projected-set shape) is `set`. */
const cardinalityFromResultType = (resultType: string): QueryBindingNode['cardinality'] => {
  if (resultType.startsWith('optional[')) return 'optional'
  if (resultType.startsWith('entities[') || resultType.startsWith('connections[') || resultType.startsWith('list[')) return 'set'
  return 'instance'
}

// ── parameters ────────────────────────────────────────────────────────────────

export const parameterToMapping = (parameter: QueryParameterNode): Record<string, unknown> => {
  const result: Record<string, unknown> = { name: parameter.name, type: parameter.valueType }
  if (parameter.cardinality === 'many') {
    result.cardinality = 'many'
    if (parameter.allowedValues.length > 0) result.allowed_values = [...parameter.allowedValues]
    result.min_items = parameter.minItems
  }
  if (!parameter.required) result.required = false
  if (typeof parameter.default === 'string') {
    if (parameter.default !== '') result.default = parseDefault(parameter.default, parameter.valueType)
  } else if (parameter.default.length > 0) {
    result.default = [...parameter.default]
  }
  if (parameter.description) result.description = parameter.description
  return result
}

const parseDefault = (raw: string, valueType: ParameterValueType): unknown => {
  if (valueType === 'integer') return Number.parseInt(raw, 10)
  if (valueType === 'number') return Number.parseFloat(raw)
  if (valueType === 'boolean') return raw === 'true'
  return raw
}

export const parameterFromMapping = (raw: unknown): QueryParameterNode => {
  const rec = asRecord(raw)
  const node = mkQueryParameter()
  node.name = stringOr(rec.name, '')
  node.valueType = (rec.type as ParameterValueType) ?? 'string'
  node.required = Boolean(rec.required ?? true)
  node.description = stringOr(rec.description, '')
  node.cardinality = rec.cardinality === 'many' ? 'many' : 'one'
  if (node.cardinality === 'many') {
    node.allowedValues = Array.isArray(rec.allowed_values) ? rec.allowed_values.map(String) : []
    node.minItems = typeof rec.min_items === 'number' ? rec.min_items : 1
    node.default = Array.isArray(rec.default) ? rec.default.map(String) : []
  } else {
    node.default = stringOr(rec.default, '')
  }
  return node
}

// ── derived attributes ───────────────────────────────────────────────────────

export const derivedAttributeToMapping = (attribute: DerivedAttributeNode): Record<string, unknown> => {
  const result: Record<string, unknown> = { name: attribute.name }
  if (attribute.source === 'security-signal') {
    result.source = 'security-signal'
    result.metric = attribute.metric
    return result
  }
  if (attribute.direction !== 'either') result.direction = attribute.direction
  if (attribute.traversal !== 'direct') result.traversal = attribute.traversal
  if (attribute.includePotential) result.include_potential = true
  if (attribute.maxHops !== null) result.max_hops = attribute.maxHops
  if (attribute.connectionCriteria !== null) result.connection_criteria = groupToMapping(attribute.connectionCriteria)
  if (attribute.endpointCriteria !== null) result.endpoint_criteria = groupToMapping(attribute.endpointCriteria)
  if (attribute.reduce !== 'count') result.reduce = attribute.reduce
  const of = derivedOfStringFor(attribute)
  if (of !== null) result.of = of
  return result
}

export const derivedAttributeFromMapping = (raw: unknown): DerivedAttributeNode => {
  const rec = asRecord(raw)
  const node = mkDerivedAttribute()
  node.name = stringOr(rec.name, '')
  if (rec.source === 'security-signal') {
    node.source = 'security-signal'
    node.metric = stringOrNull(rec.metric)
    return node
  }
  node.direction = (rec.direction as IncidentDirection) ?? 'either'
  node.traversal = rec.traversal === 'derived' ? 'derived' : 'direct'
  node.includePotential = Boolean(rec.include_potential ?? false)
  node.maxHops = rec.max_hops != null ? Number(rec.max_hops) : null
  node.connectionCriteria = rec.connection_criteria != null ? groupFromMapping(asRecord(rec.connection_criteria), 'connection') : null
  node.endpointCriteria = rec.endpoint_criteria != null ? groupFromMapping(asRecord(rec.endpoint_criteria), 'entity') : null
  node.reduce = (rec.reduce as DerivedAttributeNode['reduce']) ?? 'count'
  const parsedOf = derivedOfFromString(stringOrNull(rec.of))
  node.ofHead = parsedOf.head
  node.ofAttribute = parsedOf.attribute
  return node
}
