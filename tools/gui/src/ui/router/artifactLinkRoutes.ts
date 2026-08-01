import { type ArtifactArea, type ArtifactTarget, artifactTargetForHref } from '../../domain/artifactLinks'
import { diagramDetailRoute, documentDetailRoute, entityDetailRoute } from './artifactRoutes'

/**
 * The thin adapter between artifact-link *parsing* and this router's spelling of a detail route.
 *
 * The parsing is `domain/artifactLinks`, which reports the area and the id; the route templates and
 * their builders are `artifactRoutes`. Joining the two here is what keeps the domain module from
 * knowing what a Vue path looks like — and means a rename of a detail route is made in the builder
 * and nowhere else.
 */
const ROUTE_BY_AREA: Record<ArtifactArea, (id: string) => string> = {
  model: entityDetailRoute,
  docs: documentDetailRoute,
  'diagram-catalog': diagramDetailRoute,
}

/** The in-app route for a target, built by the same builder every other call site uses. */
export const artifactTargetRoute = (target: ArtifactTarget): string =>
  ROUTE_BY_AREA[target.area](target.id)

/** An artifact-file href rewritten to its in-app route, or null when it names no artifact. */
export const artifactRouteForHref = (href: string, siblingArea?: ArtifactArea): string | null => {
  const target = artifactTargetForHref(href, siblingArea)
  return target === null ? null : artifactTargetRoute(target)
}
