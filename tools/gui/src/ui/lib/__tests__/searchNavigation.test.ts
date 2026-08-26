import { ROUTE_TEMPLATES, assuranceNodeDetailRoute, diagramDetailRoute, documentDetailRoute, entityDetailRoute, scratchpadDetailRoute } from '../../router/artifactRoutes'
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

import { searchHitRoute, searchHitTypeLabel } from '../searchNavigation'

const stub = { template: '<div/>' }

// Mirrors the relevant routes declared in router/index.ts, through the same templates.
const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: ROUTE_TEMPLATES.entityDetail, component: stub },
    { path: ROUTE_TEMPLATES.diagramDetail, component: stub },
    { path: ROUTE_TEMPLATES.documentDetail, component: stub },
    { path: '/assurance/browse', component: stub },
    { path: ROUTE_TEMPLATES.assuranceNodeDetail, component: stub },
    { path: ROUTE_TEMPLATES.scratchpadDetail, component: stub },
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
      .toEqual(assuranceNodeDetailRoute('N1'))
  })

  it('routes a scratchpad to its own page, by its own id', () => {
    // The pad is addressable in a way a note is not, which is the whole reason it is a record of
    // its own: it has an id, a name someone chose, and a page. A note has none of those.
    expect(searchHitRoute({
      record_type: 'scratchpad',
      artifact_id: 'SCR@1.aa.q3-thinking',
    })).toEqual(scratchpadDetailRoute('SCR@1.aa.q3-thinking'))
  })

  it('routes a scratchpad without needing a scratchpad_id', () => {
    // The note case needs its container named because a note's own id routes nowhere. A pad is its
    // own container, so requiring the same field would be asking it to point at itself.
    expect(searchHitRoute({
      record_type: 'scratchpad',
      artifact_id: 'SCR@1.aa.q3-thinking',
      scratchpad_id: null,
    })).toEqual(scratchpadDetailRoute('SCR@1.aa.q3-thinking'))
  })

  it('routes a scratchpad note to the canvas it sits on, not to the note', () => {
    // A note has no page: its `artifact_id` is `{scratchpad_id}#note/{note_id}`, and routing to
    // that would open nothing. The useful answer is the canvas, where it can be read in context.
    expect(searchHitRoute({
      record_type: 'scratchpad-note',
      artifact_id: 'SCR@1.aa.pad#note/n1',
      scratchpad_id: 'SCR@1.aa.pad',
    })).toEqual(scratchpadDetailRoute('SCR@1.aa.pad'))
  })

  it('routes a scratchpad note nowhere when the hit did not say which scratchpad', () => {
    expect(searchHitRoute({ record_type: 'scratchpad-note', artifact_id: 'SCR@1.aa.pad#note/n1' }))
      .toBeNull()
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

describe('searchHitTypeLabel', () => {
  it('reads a diagram type rather than the constant "diagram"', () => {
    // A diagram's `artifact_type` is its kind. The specific type travels beside it and one of the two
    // readers of this question did not look.
    expect(searchHitTypeLabel({
      record_type: 'diagram', artifact_type: 'diagram', diagram_type: 'c4-deployment',
    })).toBe('c4-deployment')
  })

  it('strips the ontology prefix off an entity type', () => {
    expect(searchHitTypeLabel({ record_type: 'entity', artifact_type: 'archimate-business' }))
      .toBe('business')
  })

  it('answers null for a kind with no type of its own', () => {
    // A scratchpad. Its answer to "what type is it" is "a scratchpad", which the kind column already
    // says — and it used to carry the pad's meta-ontology here, which the prefix strip above rendered
    // as the single character `4`.
    expect(searchHitTypeLabel({ record_type: 'scratchpad', artifact_type: '' })).toBeNull()
  })

  it('does not fall back to the record kind', () => {
    // Echoing the kind into the type column tells a reader nothing twice, and it is what one of the
    // two readers did.
    expect(searchHitTypeLabel({ record_type: 'connection', artifact_type: null })).toBeNull()
  })

  it('answers null for an untyped scratchpad note rather than inventing a word', () => {
    // The view says "untyped" in its own words; putting that wording here would put it in two places.
    expect(searchHitTypeLabel({ record_type: 'scratchpad-note', artifact_type: '' })).toBeNull()
  })
})

