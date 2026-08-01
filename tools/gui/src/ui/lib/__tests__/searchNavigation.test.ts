import { ROUTE_TEMPLATES, diagramDetailRoute, documentDetailRoute, entityDetailRoute } from '../../router/artifactRoutes'
/**
 * Regression: a search hit must navigate to a route that actually exists.
 *
 * The nav-bar dropdown and the search page previously each inlined the
 * record_type -> route mapping and sent documents to `/document?id=...`, which is
 * not a declared route (the real one is `/documents/:id`), so clicking a document
 * result opened a blank page. Both now share `searchHitRoute`; this test pins the
 * mapping and proves each target resolves to a real route rather than falling
 * through to the catch-all.
 */
import { describe, it, expect } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import { searchHitRoute } from '../searchNavigation'

const stub = { template: '<div/>' }

// Mirrors the relevant routes declared in router/index.ts, through the same templates.
const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: ROUTE_TEMPLATES.entityDetail, component: stub },
    { path: ROUTE_TEMPLATES.diagramDetail, component: stub },
    { path: ROUTE_TEMPLATES.documentDetail, component: stub },
    { path: '/assurance/browse', component: stub },
    { path: '/assurance/node/:id', component: stub },
    { path: '/:pathMatch(.*)*', name: 'not-found', component: stub },
  ],
})

describe('searchHitRoute', () => {
  it('routes documents to their detail path', () => {
    expect(searchHitRoute({ record_type: 'document', artifact_id: 'STD@1.aa.x' }))
      .toBe(documentDetailRoute('STD@1.aa.x'))
  })

  it('routes entities and diagrams to their detail path', () => {
    expect(searchHitRoute({ record_type: 'entity', artifact_id: 'E1' })).toEqual(entityDetailRoute('E1'))
    expect(searchHitRoute({ record_type: 'diagram', artifact_id: 'D1' })).toEqual(diagramDetailRoute('D1'))
  })

  it('routes assurance nodes to the standalone node page', () => {
    expect(searchHitRoute({ record_type: 'assurance-node', artifact_id: 'N1' }))
      .toEqual('/assurance/node/N1')
  })

  it.each(['connection', 'assurance-edge', 'mystery'])('returns null for non-navigable %s', (rt) => {
    expect(searchHitRoute({ record_type: rt, artifact_id: 'X' })).toBeNull()
  })

  it.each(['entity', 'diagram', 'document', 'assurance-node'])('resolves %s to a real route', (rt) => {
    const target = searchHitRoute({ record_type: rt, artifact_id: 'STD@1.aa.x' })
    expect(target).not.toBeNull()
    const resolved = router.resolve(target!)
    expect(resolved.name).not.toBe('not-found')
    expect(resolved.matched.length).toBeGreaterThan(0)
  })
})
