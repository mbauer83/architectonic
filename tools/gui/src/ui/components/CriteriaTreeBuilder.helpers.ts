/**
 * Pure helpers for `CriteriaTreeBuilder.vue`: attribute/comparator/value-kind option lists
 * fed from the criteria-catalog registries snapshot, and the depth meter. Kept out of the
 * component so they're vitest-covered without mounting Vue.
 */

import type { InjectionKey, Ref } from 'vue'
import type { Comparator, ConditionNode, GroupKind, Quantifier, ValueRefKind } from '../../domain/viewpointCriteria'
import { NUMERIC_COMPARATORS, RESERVED_CONNECTION_PATHS, RESERVED_ENTITY_PATHS, STRING_PATTERN_COMPARATORS } from '../../domain/viewpointCriteria'
import type { AggregateKind } from '../../domain/viewpointBindings'
import type { CriteriaCatalog } from '../../domain'

export const AGGREGATE_CHOICES: readonly AggregateKind[] = ['count', 'sum', 'avg', 'min', 'max']
export const QUANTIFIER_CHOICES: readonly Quantifier[] = ['any', 'all']

/** Provided by the management view, injected by every builder node so a save-time
 * validation issue can highlight the exact widget it names without prop-drilling a
 * highlight flag through every recursion level. */
export const HIGHLIGHTED_NODE_ID_KEY: InjectionKey<Ref<string | null>> = Symbol('highlightedNodeId')

export const DEPTH_CAP = 4

export interface AttributeOption {
  path: string
  reserved: boolean
  declaredType: string | null // null for reserved paths (no JSON-schema type)
}

/** One flat list: reserved read-model paths first, then effective-schema attributes — the
 * "one namespace, used everywhere a path appears" the evaluator itself assumes
 * (`RegistrySnapshot.entity_attribute_types` is flat across all entity types). */
export const attributeOptions = (groupKind: GroupKind, catalog: CriteriaCatalog): AttributeOption[] => {
  const reserved = groupKind === 'entity' ? RESERVED_ENTITY_PATHS : RESERVED_CONNECTION_PATHS
  const schemaTypes = groupKind === 'entity' ? catalog.entity_attribute_types : catalog.connection_attribute_types
  const reservedOptions = reserved.map((path) => ({ path, reserved: true, declaredType: null }))
  const schemaOptions = Object.keys(schemaTypes)
    .filter((path) => !reserved.includes(path))
    .sort()
    .map((path) => ({ path, reserved: false, declaredType: schemaTypes[path] }))
  return [...reservedOptions, ...schemaOptions]
}

const NUMERIC_TYPES = new Set(['integer', 'number', 'date'])

/** Reserved paths take string comparators only (none of them are numeric/date); a schema
 * attribute's numeric comparators gate on its declared type. `like`/`ilike` are only
 * offered for string-typed attributes (reserved paths are all string-shaped; a schema
 * attribute needs a declared `string` type) — pattern matching against a number/date/
 * boolean is never a legal comparison. */
export const comparatorsFor = (attribute: AttributeOption): readonly Comparator[] => {
  const allComparators: Comparator[] = ['eq', 'neq', 'in', 'not_in', 'exists', 'absent', 'lt', 'lte', 'gt', 'gte']
  const isNumeric = attribute.declaredType !== null && NUMERIC_TYPES.has(attribute.declaredType)
  const isString = attribute.declaredType === null || attribute.declaredType === 'string'
  const base = isNumeric ? allComparators : allComparators.filter((c) => !NUMERIC_COMPARATORS.includes(c))
  return isString ? [...base, ...STRING_PATTERN_COMPARATORS] : base
}

/** The enumerable value set for an attribute, or null for a free-text value input. `type`
 * and `specialization` draw from their dedicated registry lists; every other enumerable
 * path — schema attributes declaring a JSON-schema `enum`, plus the reserved read-model
 * facets `domain`/`status` — is served from the catalog's per-kind `*_attribute_enums` map
 * (the backend merges reserved facets into it). Anything absent stays free text; a
 * fabricated choice list is never invented. */
export const enumChoicesFor = (attribute: string, groupKind: GroupKind, catalog: CriteriaCatalog): string[] | null => {
  if (attribute === 'type') return groupKind === 'entity' ? [...catalog.entity_types] : [...catalog.connection_types]
  if (attribute === 'specialization') return [...catalog.specialization_slugs]
  const enums = groupKind === 'entity' ? catalog.entity_attribute_enums : catalog.connection_attribute_enums
  const choices = enums[attribute]
  return choices && choices.length > 0 ? [...choices] : null
}

/** Value paths that reference an entity by id — these take the entity picker (search over
 * the real repository) rather than a text field or a dropdown, since the id space is open
 * and large. Currently the reserved `id` path only (in both entity and connection
 * contexts); no schema attribute declares an entity-reference type today. */
export const isEntityReferencePath = (attribute: string): boolean => attribute === 'id'

/** Display labels for reserved paths whose raw name undersells what they filter on:
 * `group` is the project/directory membership facet, so surface that in the picker. */
const ATTRIBUTE_PATH_LABELS: Readonly<Record<string, string>> = { group: 'group (project)' }

export const attributeOptionLabel = (option: AttributeOption): string =>
  ATTRIBUTE_PATH_LABELS[option.path] ?? option.path

export interface ValueKindOption {
  kind: ValueRefKind
  label: string
}

/** `attribute_of_endpoint` (source/target) is connection-condition-only: it reads an
 * attribute off the OTHER endpoint of the connection being evaluated — meaningless for an
 * entity condition, which has no endpoints. `binding`/`parameter` are only offered once at
 * least one exists (nothing to reference otherwise — never a dead-end selection). */
export const valueKindOptions = (groupKind: GroupKind, hasBindings = false, hasParameters = false): ValueKindOption[] => {
  const options: ValueKindOption[] = [
    { kind: 'literal', label: 'a fixed value' },
    { kind: 'self', label: `another attribute of this ${groupKind === 'connection' ? 'connection' : 'entity'}` },
  ]
  if (groupKind === 'connection') {
    options.push(
      { kind: 'source', label: "the source entity's attribute" },
      { kind: 'target', label: "the target entity's attribute" },
    )
  }
  if (hasBindings) options.push({ kind: 'binding', label: 'a named binding' })
  if (hasParameters) options.push({ kind: 'parameter', label: 'a supplied parameter' })
  return options
}

export const depthLabel = (depth: number): string => `nesting ${depth + 1} of ${DEPTH_CAP}`
export const atDepthCap = (depth: number): boolean => depth + 1 >= DEPTH_CAP

/** Edit-time coherence check for one condition row — the same faults the server rejects
 * at save time ("exists takes no value", numeric comparator without a numeric/date
 * value, an empty membership list), surfaced while the row is being edited instead of as
 * a save-time dead end. Null = coherent. */
export const conditionCoherenceIssue = (node: ConditionNode): string | null => {
  const value = node.value
  if (node.comparator === 'exists' || node.comparator === 'absent') {
    const hasValue = !(value.kind === 'literal' && (value.literal === null || value.literal === ''))
    return hasValue ? `'${node.comparator}' takes no value` : null
  }
  if (value.kind !== 'literal') return null
  if (node.comparator === 'in' || node.comparator === 'not_in') {
    return Array.isArray(value.literal) && value.literal.length === 0 ? `'${node.comparator}' needs at least one value` : null
  }
  if ((NUMERIC_COMPARATORS as readonly string[]).includes(node.comparator)) {
    const raw = value.literal
    if (raw === null || raw === undefined || raw === '') return null
    if (typeof raw !== 'string' && typeof raw !== 'number') return `'${node.comparator}' needs a number or date`
    const text = String(raw)
    const numeric = !Number.isNaN(Number(text)) || !Number.isNaN(Date.parse(text))
    return numeric ? null : `'${node.comparator}' needs a number or date`
  }
  return null
}
