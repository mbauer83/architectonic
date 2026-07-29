import type { ProjectedOccurrence, ViewpointProjection } from '../../domain'

/** Companion plan §6.2 exclusion reasons — "why excluded" hint text for the ghost/hide
 * overlay, one clause per reason (a connection can carry more than one, e.g. an excluded
 * endpoint whose own criteria also mismatch). */
const REASON_HINTS: Record<ProjectedOccurrence['reasons'][number], string> = {
  out_of_scope: 'out of scope for the applied viewpoint',
  criteria_mismatch: "does not match the viewpoint's query criteria",
  endpoint_excluded: 'one of its endpoints is excluded',
}

export const reasonHint = (reasons: readonly ProjectedOccurrence['reasons'][number][]): string | null =>
  reasons.length === 0 ? null : `Excluded: ${reasons.map((r) => REASON_HINTS[r]).join('; ')}`

export type OcclusionRenderState = 'visible' | 'ghosted' | 'hidden'

/** The per-surface "hide instead of ghost" toggle (§6.2) is a rendering choice over the
 * same contract state, never a distinct projection value — this is where that choice
 * is applied. */
export const effectiveOcclusionState = (
  occurrence: Pick<ProjectedOccurrence, 'state'>, hideInsteadOfGhost: boolean,
): OcclusionRenderState =>
  occurrence.state === 'ghosted' && hideInsteadOfGhost ? 'hidden' : occurrence.state

export const projectionByItemId = (
  projection: ViewpointProjection | null,
): ReadonlyMap<string, ProjectedOccurrence> =>
  new Map((projection?.items ?? []).map((item) => [item.item_id, item]))
