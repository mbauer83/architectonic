import type { AuthoringGuidance, EntityTypeGuidance } from '../../domain'

/**
 * Every wizard-created entity carries this tag so an abandoned session's leftovers stay
 * discoverable later via an ordinary keyword filter (decision D-6) instead of silently blending
 * into hand-created drafts.
 */
export const WIZARD_DRAFT_KEYWORD = 'wizard-draft'

/**
 * `GET /api/authoring-guidance?domain=...` (the wizard's only real call pattern) omits the
 * per-item `domain` field entirely — the whole response is already domain-scoped server-side, so
 * stamping the same value onto every entry would be redundant (see
 * `_entity_type_guidance`'s `include_domain` in `type_guidance.py`). Trust that scoping when the
 * field is absent; still filter defensively for a hypothetical unfiltered/multi-domain response
 * where the backend does stamp it.
 */
export const entityTypesForDomain = (
  guidance: AuthoringGuidance | null,
  domain: string,
): EntityTypeGuidance[] =>
  (guidance?.entity_types ?? [])
    .filter((entityType) => entityType.domain === undefined || entityType.domain === domain)

/**
 * Splits a domain's entity types into a small, question-phrased "visible" set (never the full
 * type palette) and the rest, revealed only on request. `priorityTypes` (the domain
 * questionnaire's spine step types — the content-driven ranking signal from WU-B2c) float to the
 * front of the visible slice in their given order; without them the split is a plain first-N
 * slice of the guidance API's own (alphabetical) order.
 */
export function splitVisibleEntityTypes(
  entityTypes: readonly EntityTypeGuidance[],
  maxVisible = 4,
  priorityTypes: readonly string[] = [],
): { visible: EntityTypeGuidance[]; rest: EntityTypeGuidance[] } {
  const rank = (t: EntityTypeGuidance) => {
    const index = priorityTypes.indexOf(t.name)
    return index === -1 ? priorityTypes.length : index
  }
  const ordered = [...entityTypes].sort((a, b) => rank(a) - rank(b))
  return { visible: ordered.slice(0, maxVisible), rest: ordered.slice(maxVisible) }
}
