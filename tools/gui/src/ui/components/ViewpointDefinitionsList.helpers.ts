/**
 * Pure helpers for the viewpoint catalog list: per-definition display metadata
 * (representation glyph, needs-input marker, collapsed scope summary) and the
 * search / tier-filter / sort pipeline the list renders through.
 */

import type { ScopeSummary, ViewpointDefinitionEnvelope } from '../../domain'
import type { Representation } from '../../domain/viewpointPresentation'
import { presentationFromMapping } from '../../domain/viewpointPresentationSerialization'
import { needsParameterPrompt, parameterSignatureOf } from '../lib/viewpointExecutionParameters'

export const representationOf = (envelope: ViewpointDefinitionEnvelope): Representation =>
  presentationFromMapping(envelope.presentation)?.representation ?? 'exploration'

/** Glyph + word per representation — recognition over recall in the catalog and pickers. */
export const REPRESENTATION_BADGES: Record<Representation, { glyph: string; label: string }> = {
  exploration: { glyph: '◉', label: 'exploration' },
  table: { glyph: '▦', label: 'table' },
  matrix: { glyph: '▤', label: 'matrix' },
  diagram: { glyph: '⬡', label: 'diagram' },
}

/** True when executing this definition will prompt for input first (at least one
 * required, undefaulted parameter). */
export const definitionNeedsInput = (envelope: ViewpointDefinitionEnvelope): boolean =>
  needsParameterPrompt(parameterSignatureOf(envelope))

/** How many authored references in this definition no longer resolve against the current
 * model — the count the catalogue badge shows. */
export const brokenReferenceCount = (envelope: ViewpointDefinitionEnvelope): number =>
  (envelope.broken_references ?? []).length

/** Tooltip enumerating each broken reference (locus + what it names), so the badge
 * explains itself on hover without opening the editor. */
export const brokenReferenceSummary = (envelope: ViewpointDefinitionEnvelope): string =>
  (envelope.broken_references ?? [])
    .map((broken) => `${broken.locus}: '${broken.reference}' no longer exists`)
    .join('\n')

/** One-line scope summary with the type dumps collapsed to counts — the full lists
 * stay one toggle away, they just don't dominate the catalog row. */
export const collapsedScopeSummary = (summary: ScopeSummary): string => {
  if (summary.unrestricted) return 'unrestricted'
  const parts: string[] = []
  const count = (label: string, values: readonly string[] | undefined) => {
    if (values && values.length > 0) parts.push(`${values.length} ${label}${values.length === 1 ? '' : 's'}`)
  }
  count('entity type', summary.entity_types)
  count('connection type', summary.connection_types)
  count('excluded domain', summary.excluded_domains)
  count('excluded entity type', summary.excluded_entity_types)
  count('excluded connection type', summary.excluded_connection_types)
  return parts.join(', ') || 'unrestricted'
}

export type CatalogSortKey = 'name' | 'version' | 'tier'
export type CatalogSortDirection = 'asc' | 'desc'

const TIER_ORDER: Record<ViewpointDefinitionEnvelope['tier'], number> = {
  engagement: 0, enterprise: 1, module: 2,
}

/** Search (name/slug/description, case-insensitive) → tier filter → sort. No search and
 * no sort key preserves the catalog's served order. */
export const filterAndSortDefinitions = (
  definitions: readonly ViewpointDefinitionEnvelope[],
  search: string,
  tier: ViewpointDefinitionEnvelope['tier'] | '',
  sortKey: CatalogSortKey | null,
  direction: CatalogSortDirection,
): readonly ViewpointDefinitionEnvelope[] => {
  const needle = search.trim().toLowerCase()
  const matches = definitions.filter((definition) =>
    (tier === '' || definition.tier === tier)
    && (needle === ''
      || definition.slug.toLowerCase().includes(needle)
      || definition.name.toLowerCase().includes(needle)
      || (definition.description ?? '').toLowerCase().includes(needle)),
  )
  if (sortKey === null) return matches
  const factor = direction === 'asc' ? 1 : -1
  return [...matches].sort((a, b) => {
    if (sortKey === 'version') return (a.version - b.version) * factor
    if (sortKey === 'tier') return (TIER_ORDER[a.tier] - TIER_ORDER[b.tier]) * factor
    return a.name.localeCompare(b.name) * factor
  })
}

/** The one line of capability copy shared by the create button and the empty state —
 * creation is a first-class route, distinct from forking via Save as. */
export const CREATE_CAPABILITY_COPY =
  'Build your own view — filter by type, project, status, or connections.'


/** Column-sort cycling: same key toggles direction, a new key starts ascending. */
export const nextCatalogSort = (
  currentKey: CatalogSortKey | null,
  currentDirection: CatalogSortDirection,
  clicked: CatalogSortKey,
): { key: CatalogSortKey; direction: CatalogSortDirection } =>
  currentKey === clicked
    ? { key: clicked, direction: currentDirection === 'asc' ? 'desc' : 'asc' }
    : { key: clicked, direction: 'asc' }

/** Immutable membership toggle for the expanded-scope set. */
export const toggledMember = (members: ReadonlySet<string>, slug: string): Set<string> => {
  const next = new Set(members)
  if (next.has(slug)) next.delete(slug)
  else next.add(slug)
  return next
}
