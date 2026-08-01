import { describe, expect, it } from 'vitest'
import { artifactRouteForHref } from './artifactLinkRoutes'
import { diagramDetailRoute, documentDetailRoute, entityDetailRoute } from './artifactRoutes'

/**
 * The adapter's own job: an area and an id become the route the builders spell.
 *
 * Asserted against the builders rather than against literal paths, deliberately. A literal here
 * would be a second declaration of the route, and the migration's whole point is that there is one.
 * What this pins is the *mapping* — that a `model` href lands on the entity route and not the
 * diagram one — which a literal would not check any better.
 */
describe('artifactRouteForHref', () => {
  it('routes each area to that area’s detail builder', () => {
    expect(artifactRouteForHref('model/motivation/requirement/REQ@1.Ab.x.md'))
      .toBe(entityDetailRoute('REQ@1.Ab.x'))
    expect(artifactRouteForHref('docs/adr/ADR@1.Ab.y.md'))
      .toBe(documentDetailRoute('ADR@1.Ab.y'))
    expect(artifactRouteForHref('diagram-catalog/diagrams/CC@1.Ab.z.puml'))
      .toBe(diagramDetailRoute('CC@1.Ab.z'))
  })

  it('routes a same-directory link using the rendering artifact’s area', () => {
    expect(artifactRouteForHref('ADR@1.Ab.y.md', 'docs')).toBe(documentDetailRoute('ADR@1.Ab.y'))
  })

  it('is null for an href that names no artifact', () => {
    expect(artifactRouteForHref('https://example.com/model/REQ@1.Ab.x.md')).toBeNull()
    expect(artifactRouteForHref('somewhere/REQ@1.Ab.x.md')).toBeNull()
  })
})
