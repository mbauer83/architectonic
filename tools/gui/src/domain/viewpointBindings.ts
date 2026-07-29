/**
 * Query bindings, parameters, and derived attributes — mirrors
 * `src/domain/viewpoints/viewpoint_bindings.py` field for field (that backend module is itself split
 * out of `viewpoint_criteria.py`, so this mirrors the split too). Each node carries a
 * UI-only `id` (never serialized), same convention as `viewpointCriteria.ts`.
 */

import { type GroupKind, type GroupNode, type IncidentDirection, mkGroup, nextNodeId } from './viewpointCriteria'

export type BindingSelect = 'entities' | 'connections'
export type AggregateKind = 'count' | 'sum' | 'avg' | 'min' | 'max'
export type ScalarKind = 'string' | 'integer' | 'number' | 'date' | 'boolean' | 'slug'
export type ParameterValueType = ScalarKind | 'entity-id'
export type DerivedTraversal = 'direct' | 'derived'

/** A binding's declared cardinality — simultaneously a static type and (for `instance`/
 * `optional`) a runtime assertion on the resolved selection's size. Independent of
 * `project`/`aggregate`, which further transform the selected entities/connections into a
 * scalar or reduced value without changing which cardinality was declared. */
export type BindingCardinality = 'instance' | 'optional' | 'set'

export const bindingGroupKind = (select: BindingSelect): GroupKind => (select === 'entities' ? 'entity' : 'connection')

export interface QueryBindingNode {
  readonly id: string
  name: string
  mode: 'select' | 'tuple'
  select: BindingSelect
  criteria: GroupNode
  cardinality: BindingCardinality
  project: string | null
  aggregate: AggregateKind | null
  tupleOf: string[]
  includeInResult: boolean
}

export const mkQueryBinding = (): QueryBindingNode => ({
  id: nextNodeId(), name: '', mode: 'select', select: 'entities', criteria: mkGroup('entity'),
  cardinality: 'set', project: null, aggregate: null, tupleOf: [], includeInResult: false,
})

/** `one` = a scalar value; `many` = an ordered set. Orthogonal to `valueType` (the element
 * kind), mirroring the backend: a closed set of strings and an open set of slugs differ only
 * by `allowedValues`. */
export type ParameterCardinality = 'one' | 'many'

export interface QueryParameterNode {
  readonly id: string
  name: string
  valueType: ParameterValueType
  required: boolean
  /** A scalar default is a string; a set default is its member list. Empty string / empty
   * array both mean "no default". */
  default: string | readonly string[]
  description: string
  cardinality: ParameterCardinality
  /** Non-empty = a CLOSED vocabulary (members enforced); empty = OPEN (any value accepted,
   * an unmatched one yielding an empty result rather than an error). `many` only. */
  allowedValues: readonly string[]
  minItems: number
}

export const mkQueryParameter = (): QueryParameterNode => ({
  id: nextNodeId(), name: '', valueType: 'string', required: true, default: '', description: '',
  cardinality: 'one', allowedValues: [], minItems: 1,
})

export type DerivedOfHead = 'none' | 'connection' | 'endpoint' | 'relationship-hops'

export interface DerivedAttributeNode {
  readonly id: string
  name: string
  /** 'graph' attributes are computed from the model graph; 'security-signal'
   * attributes are batch-fetched metrics — the graph fields below are
   * meaningless for them and never serialized. */
  source: 'graph' | 'security-signal'
  metric: string | null
  direction: IncidentDirection
  traversal: DerivedTraversal
  includePotential: boolean
  maxHops: number | null
  connectionCriteria: GroupNode | null
  endpointCriteria: GroupNode | null
  reduce: AggregateKind
  ofHead: DerivedOfHead
  ofAttribute: string | null
}

export const mkDerivedAttribute = (): DerivedAttributeNode => ({
  id: nextNodeId(), name: '', source: 'graph', metric: null,
  direction: 'either', traversal: 'direct', includePotential: false, maxHops: null,
  connectionCriteria: null, endpointCriteria: null, reduce: 'count', ofHead: 'none', ofAttribute: null,
})

/** Conservative type-union inference from a binding's own criteria, mirroring the
 * backend's `infer_binding_type` rule: the union of literal `type` values from positive
 * (non-negated) `eq`/`in` conditions on the criteria's top-level AND spine. Never claims a
 * narrower union than provable — anything else (OR-conjunction, nested groups, non-`type`
 * conditions) leaves the union open (empty = any type). Save-mode validation is the
 * authority on whether a declared binding is actually compatible; this only drives what
 * gets written to the wire and the live "you're building" readout. */
export const inferTypeUnion = (criteria: GroupNode): readonly string[] => {
  if (criteria.conjunction !== 'and') return []
  const slugs = new Set<string>()
  for (const child of criteria.children) {
    if (child.kind !== 'condition' || child.negate || child.attribute !== 'type') continue
    if (child.value.kind !== 'literal') continue
    if (child.comparator === 'eq' && typeof child.value.literal === 'string') slugs.add(child.value.literal)
    if (child.comparator === 'in' && Array.isArray(child.value.literal)) {
      for (const v of child.value.literal) if (typeof v === 'string') slugs.add(v)
    }
  }
  return [...slugs].sort()
}

const instanceKind = (select: BindingSelect): 'entity' | 'connection' => (select === 'entities' ? 'entity' : 'connection')
const setKind = (select: BindingSelect): 'entities' | 'connections' => select

const slugged = (name: string, slugs: readonly string[]): string => `${name}[${slugs.join('|')}]`

/** The two flat attribute-type tables (`entity_attribute_types`/`connection_attribute_types`
 * from the criteria catalog) a `project`ed binding needs, keyed by which one its `select`
 * draws from. */
export interface AttributeTypeTables {
  entity: Readonly<Record<string, string>>
  connection: Readonly<Record<string, string>>
}

/** Pulls the two flat tables straight off a `CriteriaCatalog` — the shape every
 * `definitionToMapping`/`queryToMapping` call site with a live catalog in scope should
 * pass, so a `project`ed binding's declared `result_type` reflects the real schema kind
 * rather than silently falling back to `string`. */
export const attributeTypeTablesFromCatalog = (catalog: {
  entity_attribute_types: Readonly<Record<string, string>>
  connection_attribute_types: Readonly<Record<string, string>>
}): AttributeTypeTables => ({ entity: catalog.entity_attribute_types, connection: catalog.connection_attribute_types })

/** Attribute-path scalar kind for `project`: the schema-declared type when known, else
 * `string` — reserved paths (`id`, `type`, `status`, ...) have no JSON-schema entry, and
 * their exact backend-declared kinds aren't reproduced here; a mismatch is caught by
 * save-mode validation (`binding-attribute-type-ambiguous`/`binding-type-mismatch`), never
 * silently persisted wrong. */
export const projectedScalarKind = (
  attribute: string,
  groupKind: GroupKind,
  attributeTypes: AttributeTypeTables,
): ScalarKind => {
  const declared = attributeTypes[groupKind][attribute]
  if (declared === 'integer' || declared === 'number' || declared === 'date' || declared === 'boolean' || declared === 'slug') {
    return declared
  }
  return groupKind === 'entity' && attribute === 'id' ? 'slug' : 'string'
}

/** The canonical `result_type` wire string a binding declares — the counterpart to
 * `format_result_type` in `src/domain/viewpoints/viewpoint_value_types.py`. Cardinality/project/
 * aggregate are the user's own explicit choices (the declared type doubles as a
 * cardinality assertion, so it is not purely inferred); only the type-union portion is
 * inferred from criteria. */
export const resultTypeStringFor = (
  binding: QueryBindingNode,
  allBindings: readonly QueryBindingNode[],
  attributeTypes: AttributeTypeTables,
): string => {
  if (binding.mode === 'tuple') {
    const elementTypes = binding.tupleOf.map((name) => {
      const referenced = allBindings.find((b) => b.name === name)
      return referenced ? resultTypeStringFor(referenced, allBindings, attributeTypes) : 'string'
    })
    return `tuple[${elementTypes.join(', ')}]`
  }
  const groupKind = bindingGroupKind(binding.select)
  const union = inferTypeUnion(binding.criteria)
  if (binding.aggregate === 'count') return 'integer'
  if (binding.project !== null) {
    const scalar = projectedScalarKind(binding.project, groupKind, attributeTypes)
    if (binding.aggregate !== null) return binding.aggregate === 'avg' ? 'number' : scalar
    if (binding.cardinality === 'set') return `list[${scalar}]`
    return binding.cardinality === 'optional' ? `optional[${scalar}]` : scalar
  }
  if (binding.cardinality === 'set') return slugged(setKind(binding.select), union)
  const base = slugged(instanceKind(binding.select), union)
  return binding.cardinality === 'optional' ? `optional[${base}]` : base
}

/** The `of:` string a derived attribute declares — `connection.<attr>` / `endpoint.<attr>`
 * / `relationship.hops`, or `null` when `ofHead` is `none` (legal only with `reduce:
 * count`, matching the backend's `of: str | None = None; None iff reduce=count`). */
export const derivedOfStringFor = (attribute: DerivedAttributeNode): string | null => {
  if (attribute.ofHead === 'none') return null
  if (attribute.ofHead === 'relationship-hops') return 'relationship.hops'
  return `${attribute.ofHead}.${attribute.ofAttribute ?? ''}`
}

export const derivedOfFromString = (of: string | null): { head: DerivedOfHead; attribute: string | null } => {
  if (of === null) return { head: 'none', attribute: null }
  if (of === 'relationship.hops') return { head: 'relationship-hops', attribute: null }
  const [head, ...rest] = of.split('.')
  if (head === 'connection' || head === 'endpoint') return { head, attribute: rest.join('.') }
  return { head: 'none', attribute: null }
}
