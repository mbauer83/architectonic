/**
 * Top-level `ViewpointDefinitionDraft` <-> canonical wire mapping conversion — the exact
 * counterpart of `src/domain/viewpoints/viewpoint_serialization.py` / `viewpoint_parsing.py`
 * (structural shape only; registry-aware validation happens server-side on save).
 */

import { queryFromMapping, queryToMapping } from './viewpointCriteriaSerialization'
import { presentationFromMapping, presentationToMapping } from './viewpointPresentationSerialization'
import type { AttributeTypeTables } from './viewpointBindings'
import {
  type Content,
  type Purpose,
  type ScopeDraft,
  type ViewpointDefinitionDraft,
  isEmptyQuery,
  mkDefinitionDraft,
} from './viewpointDefinitionDraft'

const asRecord = (raw: unknown): Record<string, unknown> => raw as Record<string, unknown>

/** `String(v)` on `unknown` trips `@typescript-eslint/no-base-to-string` — this narrows
 * first, matching how the Python parser's `str(raw.get(...) or default)` reads a mapping
 * value that is always either absent, a string, or a number in valid input. */
const stringOr = (v: unknown, fallback: string): string =>
  typeof v === 'string' || typeof v === 'number' ? String(v) : fallback

const tupleShorthand = (values: readonly string[]): string | string[] => (values.length === 1 ? values[0] : [...values])

const stringList = (raw: unknown, fallback: readonly string[]): string[] => {
  if (raw == null) return [...fallback]
  if (typeof raw === 'string') return [raw]
  if (Array.isArray(raw)) return raw.map(String)
  return [...fallback]
}

const scopeToMapping = (scope: ScopeDraft): Record<string, unknown> => {
  const result: Record<string, unknown> = {}
  if (scope.entityTypes !== null) result.entity_types = [...scope.entityTypes].sort()
  if (scope.connectionTypes !== null) result.connection_types = [...scope.connectionTypes].sort()
  if (scope.excludedEntityTypes.length > 0) result.excluded_entity_types = [...scope.excludedEntityTypes].sort()
  if (scope.excludedDomains.length > 0) result.excluded_domains = [...scope.excludedDomains].sort()
  if (scope.excludedConnectionTypes.length > 0) {
    result.excluded_connection_types = [...scope.excludedConnectionTypes].sort()
  }
  return result
}

const scopeFromMapping = (raw: unknown): ScopeDraft => {
  if (raw == null || typeof raw !== 'object') {
    return {
      entityTypes: null, connectionTypes: null,
      excludedEntityTypes: [], excludedDomains: [], excludedConnectionTypes: [],
    }
  }
  const rec = asRecord(raw)
  return {
    entityTypes: Array.isArray(rec.entity_types) ? rec.entity_types.map(String) : null,
    connectionTypes: Array.isArray(rec.connection_types) ? rec.connection_types.map(String) : null,
    excludedEntityTypes: stringList(rec.excluded_entity_types, []),
    excludedDomains: stringList(rec.excluded_domains, []),
    excludedConnectionTypes: stringList(rec.excluded_connection_types, []),
  }
}

const EMPTY_ATTRIBUTE_TYPES: AttributeTypeTables = { entity: {}, connection: {} }

/** `attributeTypes` defaults to empty tables, matching `queryToMapping`'s own default —
 * safe unless the draft has a binding with `project` set, in which case its declared
 * `result_type` needs the real schema kind (the criteria catalog's
 * `entity_attribute_types`/`connection_attribute_types`) to serialize accurately. Every
 * real save/test-run call site has the catalog in scope and should pass it. */
export const definitionToMapping = (
  draft: ViewpointDefinitionDraft,
  attributeTypes: AttributeTypeTables = EMPTY_ATTRIBUTE_TYPES,
): Record<string, unknown> => {
  const result: Record<string, unknown> = {
    slug: draft.slug,
    version: draft.version,
    name: draft.name,
    purpose: tupleShorthand(draft.purpose),
    content: tupleShorthand(draft.content),
  }
  if (draft.description) result.description = draft.description
  if (draft.rationale) result.rationale = draft.rationale
  if (draft.stakeholders.length > 0) result.stakeholders = draft.stakeholders
  if (draft.concerns.length > 0) result.concerns = draft.concerns
  const scope = scopeToMapping(draft.scope)
  if (Object.keys(scope).length > 0) result.scope = scope
  if (draft.representationTypes.length > 0) result.representation_types = draft.representationTypes
  if (Object.keys(draft.derivationDefaults).length > 0) result.derivation_defaults = draft.derivationDefaults
  // In scope mode a pristine (says-nothing) builder query is noise, not intent — it is
  // dropped rather than persisted as a divergent inactive layer. A NON-empty query is
  // kept as inactive history in either mode.
  const keepQuery = draft.query !== null && !(draft.selectionMode === 'scope' && isEmptyQuery(draft.query))
  if (keepQuery && draft.query !== null) result.query = queryToMapping(draft.query, attributeTypes)
  if (draft.presentation !== null) result.presentation = presentationToMapping(draft.presentation)
  // Always written: exactly one selection layer is active, and every GUI save states which.
  result.selection_mode = draft.selectionMode
  return result
}

export const definitionFromMapping = (raw: Record<string, unknown>): ViewpointDefinitionDraft => {
  const draft = mkDefinitionDraft()
  draft.slug = stringOr(raw.slug, '')
  draft.version = Number(raw.version ?? 1)
  draft.name = stringOr(raw.name, draft.slug)
  draft.description = stringOr(raw.description, '')
  draft.rationale = stringOr(raw.rationale, '')
  draft.purpose = stringList(raw.purpose, ['informing']) as Purpose[]
  draft.content = stringList(raw.content, ['overview']) as Content[]
  draft.stakeholders = stringList(raw.stakeholders, [])
  draft.concerns = stringList(raw.concerns, [])
  draft.scope = scopeFromMapping(raw.scope)
  draft.representationTypes = stringList(raw.representation_types, [])
  draft.derivationDefaults = typeof raw.derivation_defaults === 'object' && raw.derivation_defaults != null
    ? asRecord(raw.derivation_defaults) : {}
  draft.query = raw.query != null ? queryFromMapping(raw.query) : null
  draft.presentation = presentationFromMapping(raw.presentation)
  // Legacy (pre-migration) definitions carry no mode; the editor mirrors the engine's
  // legacy behavior: the query is active when present, else the scope.
  draft.selectionMode = raw.selection_mode === 'scope' || raw.selection_mode === 'query'
    ? raw.selection_mode
    : (draft.query !== null ? 'query' : 'scope')
  return draft
}
