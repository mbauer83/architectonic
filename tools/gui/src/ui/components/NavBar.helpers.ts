import type { LocationQuery } from 'vue-router'

/** The entity browser's own filter state, as it travels in the URL. */
const ENTITY_BROWSE_FILTERS = ['domain', 'view', 'type'] as const

/**
 * Where "Browse" goes, keeping the filters you already have.
 *
 * Only from inside the entity browser. `type` names an *entity* type there and a *diagram* type on
 * the diagram pages, so carrying it across sent `?type=archimate-business` into the browser as a
 * filter no entity can match: the select showed blank and the list showed nothing, until some other
 * action happened to reset it. Filters belong to the surface that defines them, and there are none
 * to preserve when you are not on it.
 */
export const browseTarget = (
  path: string, query: LocationQuery,
): string | { path: string, query: Record<string, string> } => {
  if (!isEntityBrowse(path)) return '/entities'
  const carried = Object.fromEntries(
    ENTITY_BROWSE_FILTERS
      .map((key) => [key, query[key]] as const)
      .filter((entry): entry is readonly [typeof ENTITY_BROWSE_FILTERS[number], string] =>
        typeof entry[1] === 'string' && entry[1] !== ''),
  )
  return Object.keys(carried).length ? { path: '/entities', query: carried } : '/entities'
}

/** The browser itself, not an entity's own pages — those carry no list filters. */
const isEntityBrowse = (path: string): boolean => path === '/entities' || path === '/global/entities'
