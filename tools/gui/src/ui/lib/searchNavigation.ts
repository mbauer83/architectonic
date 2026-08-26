import {
  assuranceNodeDetailRoute, diagramDetailRoute, documentDetailRoute, entityDetailRoute,
  scratchpadDetailRoute,
} from '../router/artifactRoutes'
import type { RouteLocationRaw } from 'vue-router'

/** Minimal shape of a search hit needed to decide where it navigates. */
export interface NavigableHit {
  readonly record_type: string
  readonly artifact_id: string
  /** A scratchpad note's container. A note has no page of its own — it is a card on a canvas — so
   * this is the address it navigates to, and the note's own id would route nowhere. */
  readonly scratchpad_id?: string | null
}

/**
 * The route a search hit navigates to, or `null` when the record type is not an
 * independently navigable destination (e.g. connections, assurance edges).
 *
 * Single source of truth shared by the nav-bar dropdown and the search page so the two cannot
 * drift — and built from the route builders rather than spelled here, so it cannot drift from the
 * router either.
 */
export function searchHitRoute(hit: NavigableHit): RouteLocationRaw | null {
  switch (hit.record_type) {
    case 'entity':
      return entityDetailRoute(hit.artifact_id)
    case 'diagram':
      return diagramDetailRoute(hit.artifact_id)
    case 'document':
      return documentDetailRoute(hit.artifact_id)
    case 'scratchpad':
      // The pad itself: its own page, reached by its own id. A pad is addressable in a way a note
      // is not, which is the whole reason it is a record of its own.
      return scratchpadDetailRoute(hit.artifact_id)
    case 'scratchpad-note':
      // The canvas the thought is on. A note is not a page: it is a card, and the useful answer to
      // "where is this?" is the scratchpad it sits on, opened so the note can be read in context.
      return hit.scratchpad_id ? scratchpadDetailRoute(hit.scratchpad_id) : null
    case 'assurance-node':
      // Standalone page: a search hit is a direct answer, not a browsing session. Still the legacy
      // spelling: the assurance route table is converted in its own slice, and pointing here at
      // `assuranceNodeDetailRoute` before that would emit a path nothing serves.
      return assuranceNodeDetailRoute(hit.artifact_id)
    default:
      return null
  }
}
