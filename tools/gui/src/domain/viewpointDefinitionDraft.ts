/**
 * The management view's editable draft — mirrors `ViewpointDefinition` in
 * `src/domain/viewpoints/viewpoints.py`. `scope` is the authored subset of `ConceptScope`
 * (`viewpoint_serialization._scope_to_mapping`): entity/connection-type allow-lists
 * (`null` = unrestricted), plus the exclusion fields (`excludedEntityTypes`,
 * `excludedDomains`, `excludedConnectionTypes`) that subtract from whatever the allow
 * side admits. `ConceptScope`'s class/hierarchy-inclusion predicates and endpoint rules
 * are not part of the authored shape and so are not editable here.
 */

import { type ExecutableQueryNode, literalValue, mkCondition, mkGroup, mkQuery } from './viewpointCriteria'
import { type PresentationNode } from './viewpointPresentation'

export type Purpose = 'designing' | 'deciding' | 'informing'
export type Content = 'details' | 'coherence' | 'overview'

export const VALID_PURPOSES: readonly Purpose[] = ['designing', 'deciding', 'informing']
export const VALID_CONTENTS: readonly Content[] = ['details', 'coherence', 'overview']

export interface ScopeDraft {
  entityTypes: string[] | null
  connectionTypes: string[] | null
  excludedEntityTypes: string[]
  excludedDomains: string[]
  excludedConnectionTypes: string[]
}

export const mkScope = (): ScopeDraft => ({
  entityTypes: null,
  connectionTypes: null,
  excludedEntityTypes: [],
  excludedDomains: [],
  excludedConnectionTypes: [],
})

export type SelectionMode = 'scope' | 'query'

export interface ViewpointDefinitionDraft {
  slug: string
  version: number
  name: string
  description: string
  rationale: string
  purpose: Purpose[]
  content: Content[]
  stakeholders: string[]
  concerns: string[]
  scope: ScopeDraft
  representationTypes: string[]
  derivationDefaults: Record<string, unknown>
  query: ExecutableQueryNode | null
  presentation: PresentationNode | null
  /** Which selection layer is ACTIVE — exactly one ever executes. The inactive layer is
   * kept as visible-but-disabled history; switching modes never destroys it. */
  selectionMode: SelectionMode
}

export const mkDefinitionDraft = (): ViewpointDefinitionDraft => ({
  slug: '', version: 1, name: '', description: '', rationale: '',
  purpose: ['informing'], content: ['overview'], stakeholders: [], concerns: [],
  scope: mkScope(), representationTypes: [], derivationDefaults: {},
  query: mkQuery(), presentation: null, selectionMode: 'query',
})

/** One-way scope→query conversion: the scope's entity-type allow-list becomes an
 * explicit `type in [...]` criteria group — the same mechanical translation the engine
 * applies when executing scope mode, so converting then saving changes nothing about
 * what the definition selects. */
export const queryFromScopeDraft = (scope: ScopeDraft): ExecutableQueryNode => {
  const query = mkQuery()
  if (scope.entityTypes !== null && scope.entityTypes.length > 0) {
    const condition = mkCondition('type', 'in')
    condition.value = literalValue([...scope.entityTypes].sort())
    const group = mkGroup('entity')
    group.children = [condition]
    query.entityCriteria = group
  }
  return query
}

/** True when a query says nothing at all — no criteria, parameters, bindings, derived
 * attributes, inclusions, or connection narrowing. A pristine builder query in scope
 * mode is noise, not intent, and is dropped rather than persisted. */
export const isEmptyQuery = (query: ExecutableQueryNode | null): boolean =>
  query === null
  || (query.entityCriteria.children.length === 0
    && !query.entityCriteria.negate
    && query.parameters.length === 0
    && query.bindings.length === 0
    && query.derived.length === 0
    && query.tracePatterns.length === 0
    && query.includeConnected.length === 0
    && query.connections.enabled
    && query.connections.criteria.children.length === 0
    && query.connections.traversal === 'direct')
