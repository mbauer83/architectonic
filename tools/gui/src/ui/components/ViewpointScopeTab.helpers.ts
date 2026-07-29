/**
 * Pure logic for the scope tab's entity/connection type pickers: domain grouping,
 * unrestricted/include/exclude mode derivation and transitions, and inherited-vs-explicit
 * exclusion resolution for the domain-bulk-exclude-with-per-type-carve-out pattern.
 */
import type { ScopeDraft } from '../../domain/viewpointDefinitionDraft'

export type ScopeMode = 'unrestricted' | 'include' | 'exclude'

export interface DomainGroup {
  readonly domain: string
  readonly types: readonly string[]
}

/** Groups `types` by their owning domain (`catalog.entity_type_domains`), sorted by
 * domain then type — the browse structure the entity-type picker renders. */
export const groupByDomain = (types: readonly string[], domains: Record<string, string>): DomainGroup[] => {
  const byDomain = new Map<string, string[]>()
  for (const t of types) {
    const domain = domains[t] ?? '(unknown)'
    const bucket = byDomain.get(domain)
    if (bucket) bucket.push(t)
    else byDomain.set(domain, [t])
  }
  return [...byDomain.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([domain, members]) => ({ domain, types: [...members].sort() }))
}

export const entityScopeMode = (scope: ScopeDraft): ScopeMode => {
  if (scope.entityTypes !== null) return 'include'
  if (scope.excludedEntityTypes.length > 0 || scope.excludedDomains.length > 0) return 'exclude'
  return 'unrestricted'
}

export const connectionScopeMode = (scope: ScopeDraft): ScopeMode => {
  if (scope.connectionTypes !== null) return 'include'
  if (scope.excludedConnectionTypes.length > 0) return 'exclude'
  return 'unrestricted'
}

/** Switching axis mode is a clean transition between the three mutually exclusive
 * authoring shapes this picker presents — not a general merge, since the backend's
 * include-list and exclusion fields are independent mechanisms this picker has no UI for
 * combining. Switching away from a mode clears that mode's fields so the picker never
 * shows stale, hidden state. */
export const withEntityScopeMode = (scope: ScopeDraft, mode: ScopeMode): ScopeDraft => {
  if (mode === 'unrestricted') return { ...scope, entityTypes: null, excludedEntityTypes: [], excludedDomains: [] }
  if (mode === 'include') return { ...scope, entityTypes: scope.entityTypes ?? [], excludedEntityTypes: [], excludedDomains: [] }
  return { ...scope, entityTypes: null }
}

export const withConnectionScopeMode = (scope: ScopeDraft, mode: ScopeMode): ScopeDraft => {
  if (mode === 'unrestricted') return { ...scope, connectionTypes: null, excludedConnectionTypes: [] }
  if (mode === 'include') return { ...scope, connectionTypes: scope.connectionTypes ?? [], excludedConnectionTypes: [] }
  return { ...scope, connectionTypes: null }
}

export const toggleInList = (list: readonly string[], value: string): string[] =>
  list.includes(value) ? list.filter((v) => v !== value) : [...list, value]

export type ExclusionState = 'inherited' | 'explicit' | 'none'

/** Whether `type` (in `domain`) is excluded, and whether that's because its whole domain
 * is bulk-excluded ("inherited") or because it was individually added ("explicit") — a
 * domain-level exclusion always wins the display even if the type also happens to be
 * individually listed. */
export const entityExclusionState = (
  type: string,
  domain: string,
  excludedDomains: readonly string[],
  excludedEntityTypes: readonly string[],
): ExclusionState => {
  if (excludedDomains.includes(domain)) return 'inherited'
  if (excludedEntityTypes.includes(type)) return 'explicit'
  return 'none'
}

/** Bulk-exclude a whole domain: add it to `excludedDomains` and drop any now-redundant
 * per-type entries it already covers (they'd otherwise linger as dead weight). */
export const excludeDomain = (scope: ScopeDraft, domain: string, typesInDomain: readonly string[]): ScopeDraft => ({
  ...scope,
  excludedDomains: [...new Set([...scope.excludedDomains, domain])],
  excludedEntityTypes: scope.excludedEntityTypes.filter((t) => !typesInDomain.includes(t)),
})

export const reincludeDomain = (scope: ScopeDraft, domain: string): ScopeDraft => ({
  ...scope,
  excludedDomains: scope.excludedDomains.filter((d) => d !== domain),
})

/** Carve `type` back out of its domain's bulk exclusion: replace the domain-level
 * exclusion with explicit exclusions for every OTHER type known in that domain today.
 * This keeps today's admitted set unchanged for everything but `type`, at the cost of no
 * longer auto-excluding future types added to the domain later — an inherent trade-off of
 * expanding a hierarchy predicate into an enumerated one, not hidden from the caller. */
export const carveOutFromDomainExclusion = (
  scope: ScopeDraft,
  type: string,
  domain: string,
  allTypesInDomain: readonly string[],
): ScopeDraft => {
  const siblings = allTypesInDomain.filter((t) => t !== type)
  const excludedEntityTypes = [...new Set([...scope.excludedEntityTypes, ...siblings])]
  return { ...scope, excludedDomains: scope.excludedDomains.filter((d) => d !== domain), excludedEntityTypes }
}

export const includeDomain = (scope: ScopeDraft, typesInDomain: readonly string[]): ScopeDraft => ({
  ...scope,
  entityTypes: [...new Set([...(scope.entityTypes ?? []), ...typesInDomain])],
})

export const excludeDomainFromIncludeList = (scope: ScopeDraft, typesInDomain: readonly string[]): ScopeDraft => ({
  ...scope,
  entityTypes: (scope.entityTypes ?? []).filter((t) => !typesInDomain.includes(t)),
})

export const filterByQuery = (types: readonly string[], query: string): string[] => {
  const q = query.trim().toLowerCase()
  if (!q) return [...types]
  return types.filter((t) => t.toLowerCase().includes(q))
}
