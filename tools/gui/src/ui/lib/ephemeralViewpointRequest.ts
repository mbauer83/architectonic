/**
 * Pure request-builder for the ephemeral Query-model page (§5). Kept out of the SFC so the
 * distinction that matters — inline query vs. saved-slug override — is unit-testable without
 * mounting the view.
 */
import { queryToMapping } from '../../domain/viewpointCriteriaSerialization'
import { presentationToMapping } from '../../domain/viewpointPresentationSerialization'
import { attributeTypeTablesFromCatalog } from '../../domain/viewpointBindings'
import type { ExecutableQueryNode } from '../../domain/viewpointCriteria'
import type { PresentationNode } from '../../domain/viewpointPresentation'
import type { CriteriaCatalog, ViewpointExecutionRequest } from '../../domain'

/**
 * Build the execution request the Query-model page runs.
 *
 * - Override mode (`overrideSlug` set): `{ slug, presentation }` — the SAVED definition's
 *   scope/query/derivation drive the population, and it is never mutated (§5.1a).
 * - Composition mode: `{ query, presentation }` — the inline query is authoritative.
 *
 * Either way the effective `presentation` rides along so the styled/columnar/matrix result
 * matches the editor rather than any stored presentation, and the resolved runtime
 * `parameters` (from the prompt gate, empty when the query declares none) ride along so the
 * execution — and its provenance — records the values the query actually ran with.
 */
export const buildEphemeralRequest = (
  query: ExecutableQueryNode,
  presentation: PresentationNode | null,
  catalog: CriteriaCatalog,
  overrideSlug: string | null,
  parameters: Record<string, unknown> = {},
): ViewpointExecutionRequest => {
  const presentationMapping = presentation ? presentationToMapping(presentation) : undefined
  if (overrideSlug !== null) {
    return { slug: overrideSlug, presentation: presentationMapping, parameters }
  }
  return {
    query: queryToMapping(query, attributeTypeTablesFromCatalog(catalog)),
    presentation: presentationMapping,
    parameters,
  }
}
