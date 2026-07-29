/**
 * Route-scoped, in-memory hand-off for the "Save as viewpoint…" flow (§5.4).
 *
 * The ephemeral Query-model page transfers its current query + presentation drafts into the
 * full `/viewpoints/new` editor WITHOUT persisting anything: no repository write, no
 * `localStorage`/`sessionStorage`, no long query-string. This module holds the pending draft
 * in a module-level singleton that `/viewpoints/new` consumes exactly once. A full browser
 * reload clears it (module state is reconstructed) — that loss is acceptable, and the query
 * page warns before navigating away with an unsaved, untransferred draft.
 */

import type { ExecutableQueryNode } from '../../domain/viewpointCriteria'
import type { PresentationNode } from '../../domain/viewpointPresentation'

export interface EphemeralViewpointDraft {
  readonly query: ExecutableQueryNode | null
  readonly presentation: PresentationNode | null
}

let pending: EphemeralViewpointDraft | null = null

/** Stage a query + presentation for the next `/viewpoints/new` load to adopt. */
export const stageEphemeralViewpointDraft = (draft: EphemeralViewpointDraft): void => {
  pending = draft
}

/** Consume (and clear) any staged draft — single-use, so a later plain `/viewpoints/new`
 * open is never contaminated by a stale hand-off. */
export const takeEphemeralViewpointDraft = (): EphemeralViewpointDraft | null => {
  const draft = pending
  pending = null
  return draft
}

/** Whether a hand-off is currently staged (for tests / defensive checks). */
export const hasStagedEphemeralViewpointDraft = (): boolean => pending !== null
