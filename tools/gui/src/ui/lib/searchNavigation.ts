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
 * Single source of truth shared by the nav-bar dropdown and the search page so the
 * two cannot drift. Targets must match the routes declared in `router/index.ts`:
 * documents use the REST-style path param (`/documents/:id`); entities and diagrams
 * currently use a query param (`?id=`).
 */
export function searchHitRoute(hit: NavigableHit): RouteLocationRaw | null {
  switch (hit.record_type) {
    case 'entity':
      return { path: '/entity', query: { id: hit.artifact_id } }
    case 'diagram':
      return { path: '/diagram', query: { id: hit.artifact_id } }
    case 'document':
      return `/documents/${hit.artifact_id}`
    case 'assurance-node':
      // Standalone page: a search hit is a direct answer, not a browsing session.
      return `/assurance/node/${encodeURIComponent(hit.artifact_id)}`
    default:
      return null
  }
}
