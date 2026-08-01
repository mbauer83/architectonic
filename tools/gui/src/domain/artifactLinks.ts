/**
 * Repository-relative artifact hrefs → the artifact they name.
 *
 * Document and entity markdown link to sibling artifacts with worktree-relative
 * hrefs (e.g. `../../../projects/x/model/motivation/requirement/REQ@….md`).
 * Rendered verbatim, the browser resolves those against the current GUI route
 * and lands on a page that does not exist. The artifact id is recoverable from
 * the filename, and the artifact kind from the repository area the path passes
 * through (`model/`, `docs/`, `diagram-catalog/`).
 *
 * This module *parses*; it does not spell routes. It used to return `/entity?id=…` strings, which
 * put Vue delivery paths in a domain module and made the model layer aware of the router — so a
 * route rename had to be made here, of all places. The adapter that maps an identified artifact to
 * a route is `ui/router/artifactLinkRoutes.ts`.
 */

const ARTIFACT_FILE = /^([A-Za-z]+@\d+\.[A-Za-z0-9_-]+\..+?)(\.outgoing)?\.(md|puml)$/

const hasScheme = (href: string): boolean => /^[a-z][a-z0-9+.-]*:/i.test(href) || href.startsWith('//')

/**
 * Repository area an artifact lives in. Also the fallback for a link that names no area of its
 * own — see `artifactRouteForHref`.
 */
export type ArtifactArea = 'model' | 'docs' | 'diagram-catalog'

/** What an artifact href names: the area that decides its kind, and its id. */
export interface ArtifactTarget {
  readonly area: ArtifactArea
  readonly id: string
}

/**
 * The artifact an href names, or null when it names none.
 *
 * `siblingArea` is the area of the artifact whose content is being rendered, and is what makes a
 * SAME-DIRECTORY link work. One ADR citing another writes the bare filename — no `docs/` segment
 * to read the kind from — so the href survived unrewritten, the browser resolved it against the
 * current route, and `/documents/ADR@….md` is not a route. The kind cannot be recovered from the
 * href alone in that case, and it is not this module's to guess: an id prefix belongs to whichever
 * ontology or document-type schema declares it. The caller rendering the content knows its area,
 * so it says.
 */
export function artifactTargetForHref(href: string, siblingArea?: ArtifactArea): ArtifactTarget | null {
  if (href === '' || hasScheme(href) || href.startsWith('#')) return null
  const [pathOnly] = href.split(/[?#]/)
  const rawSegments = pathOnly.split('/').filter((s) => s !== '')
  const segments = rawSegments.filter((s) => s !== '.' && s !== '..')
  const last = segments.at(-1)
  if (last === undefined) return null
  const match = ARTIFACT_FILE.exec(safeDecode(last))
  if (!match) return null
  const id = match[1]
  const declaredArea = (['model', 'docs', 'diagram-catalog'] as const).find((area) =>
    segments.includes(area),
  )
  // Only a bare filename is a sibling. `../foo/BAR@….md` names a directory this module cannot
  // classify, and guessing the current area for it would route somewhere confidently wrong.
  const area = declaredArea ?? (segments.length === 1 && rawSegments.length === 1 ? siblingArea : undefined)
  return area === undefined ? null : { area, id }
}

const safeDecode = (segment: string): string => {
  try {
    return decodeURIComponent(segment)
  } catch {
    return segment
  }
}
