/**
 * Repository-relative artifact hrefs → in-app routes.
 *
 * Document and entity markdown link to sibling artifacts with worktree-relative
 * hrefs (e.g. `../../../projects/x/model/motivation/requirement/REQ@….md`).
 * Rendered verbatim, the browser resolves those against the current GUI route
 * and lands on a page that does not exist. The artifact id is recoverable from
 * the filename, and the artifact kind from the repository area the path passes
 * through (`model/`, `docs/`, `diagram-catalog/`).
 */

const ARTIFACT_FILE = /^([A-Za-z]+@\d+\.[A-Za-z0-9_-]+\..+?)(\.outgoing)?\.(md|puml)$/

const hasScheme = (href: string): boolean => /^[a-z][a-z0-9+.-]*:/i.test(href) || href.startsWith('//')

/**
 * Repository area an artifact lives in. Also the fallback for a link that names no area of its
 * own — see `artifactRouteForHref`.
 */
export type ArtifactArea = 'model' | 'docs' | 'diagram-catalog'

const ROUTE_BY_AREA: Record<ArtifactArea, (id: string) => string> = {
  model: (id) => `/entity?id=${encodeURIComponent(id)}`,
  docs: (id) => `/documents/${encodeURIComponent(id)}`,
  'diagram-catalog': (id) => `/diagram?id=${encodeURIComponent(id)}`,
}

/**
 * Map an artifact-file href to its in-app route, or null when it is not one.
 *
 * `siblingArea` is the area of the artifact whose content is being rendered, and is what makes a
 * SAME-DIRECTORY link work. One ADR citing another writes the bare filename — no `docs/` segment
 * to read the kind from — so the href survived unrewritten, the browser resolved it against the
 * current route, and `/documents/ADR@….md` is not a route. The kind cannot be recovered from the
 * href alone in that case, and it is not this module's to guess: an id prefix belongs to whichever
 * ontology or document-type schema declares it. The caller rendering the content knows its area,
 * so it says.
 */
export function artifactRouteForHref(href: string, siblingArea?: ArtifactArea): string | null {
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
  return area === undefined ? null : ROUTE_BY_AREA[area](id)
}

const safeDecode = (segment: string): string => {
  try {
    return decodeURIComponent(segment)
  } catch {
    return segment
  }
}
