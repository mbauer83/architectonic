import {
  assuranceNodeDetailRoute, diagramDetailRoute, documentDetailRoute, entityDetailRoute,
} from '../router/artifactRoutes'
import type { RouteLocationRaw } from 'vue-router'

/** Minimal shape of a search hit needed to decide where it navigates. */
export interface NavigableHit {
  readonly record_type: string
  readonly artifact_id: string
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
    case 'assurance-node':
      // Standalone page: a search hit is a direct answer, not a browsing session. Still the legacy
      // spelling: the assurance route table is converted in its own slice, and pointing here at
      // `assuranceNodeDetailRoute` before that would emit a path nothing serves.
      return assuranceNodeDetailRoute(hit.artifact_id)
    default:
      return null
  }
}
