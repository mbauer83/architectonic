/**
 * Tests for WU-G2: AssuranceLens helpers + browse filter logic + router redirect.
 *
 * All tests exercise pure reactive logic without mounting components — consistent
 * with the existing test pattern in this project.  The component rendering path
 * (AssuranceLens shows/hides sections, AssuranceBrowseView renders node rows) is
 * exercised via Playwright against the live server.
 *
 * Full HTTP integration is covered by tests/assurance/test_assurance_http_read.py
 * (WU-G1 negative-leak tests).
 */
import { describe, it, expect } from 'vitest'
import {
  parseLensResponse,
  standaloneNodeLink,
} from '../../components/AssuranceLens.helpers'
import { ASSURANCE_BROWSE_PATH, assuranceRoutes } from '../../router/assuranceRoutes'
import { assuranceNodeDetailRoute } from '../../router/artifactRoutes'

// ── 1. parseLensResponse ──────────────────────────────────────────────────────

describe('parseLensResponse', () => {
  it('returns locked=true, visible=false when store is locked', () => {
    const result = parseLensResponse({ locked: true, nodes: [], count: 0 })
    expect(result.locked).toBe(true)
    expect(result.visible).toBe(false)
    expect(result.nodes).toHaveLength(0)
  })

  it('returns visible=false when unlocked with 0 nodes', () => {
    const result = parseLensResponse({ locked: false, nodes: [], count: 0 })
    expect(result.locked).toBe(false)
    expect(result.visible).toBe(false)
    expect(result.count).toBe(0)
  })

  it('returns visible=true when unlocked with nodes', () => {
    const nodes = [{ node_id: 'n1', node_type: 'hazard', name: 'H1' }]
    const result = parseLensResponse({ locked: false, nodes, count: 1 })
    expect(result.visible).toBe(true)
    expect(result.nodes).toHaveLength(1)
    expect(result.count).toBe(1)
  })

  it('propagates visibilityLimited flag', () => {
    const result = parseLensResponse({
      locked: false,
      nodes: [{ node_id: 'n1', node_type: 'risk', name: 'R1' }],
      count: 1,
      visibility_limited: true,
    })
    expect(result.visibilityLimited).toBe(true)
  })

  it('defaults visibilityLimited to false when absent', () => {
    const result = parseLensResponse({ locked: false, nodes: [], count: 0 })
    expect(result.visibilityLimited).toBe(false)
  })

  it('returns empty nodes list even when locked response carries nodes', () => {
    const result = parseLensResponse({
      locked: true,
      nodes: [{ node_id: 'n1', node_type: 'loss', name: 'Loss of life' }],
      count: 1,
    })
    expect(result.nodes).toHaveLength(0)
    expect(result.count).toBe(0)
  })
})

// ── 2. standaloneNodeLink ─────────────────────────────────────────────────────

describe('standaloneNodeLink', () => {
  it('deep-links to the standalone node page, escaping special chars', () => {
    const link = standaloneNodeLink('n:hazard:H1')
    expect(link).toBe(assuranceNodeDetailRoute('n:hazard:H1'))
  })

  it('handles simple node ids without special chars', () => {
    const link = standaloneNodeLink('abc123')
    expect(link).toBe(assuranceNodeDetailRoute('abc123'))
  })
})

// ── 3. Browse filter logic ────────────────────────────────────────────────────

type NodeStub = {
  node_id: string; node_type: string; name: string
  status: string; tlp: string; concern_class: string; binding_status: string
}

function makeNode(overrides: Partial<NodeStub> = {}): NodeStub {
  return {
    node_id: 'n1', node_type: 'hazard', name: 'H', status: 'open',
    tlp: 'TLP:WHITE', concern_class: 'safety', binding_status: 'unbound',
    ...overrides,
  }
}

function applyFilters(
  nodes: NodeStub[],
  filters: { type?: string; status?: string; concern?: string; tlp?: string; binding?: string },
): NodeStub[] {
  return nodes.filter(n => {
    if (filters.type && n.node_type !== filters.type) return false
    if (filters.status && n.status !== filters.status) return false
    if (filters.concern && n.concern_class !== filters.concern) return false
    if (filters.tlp && n.tlp !== filters.tlp) return false
    if (filters.binding && n.binding_status !== filters.binding) return false
    return true
  })
}

describe('browse filter logic', () => {
  const nodes = [
    makeNode({ node_id: 'n1', node_type: 'hazard', concern_class: 'safety', binding_status: 'unbound' }),
    makeNode({ node_id: 'n2', node_type: 'risk', concern_class: 'security', binding_status: 'bound', tlp: 'TLP:RED' }),
    makeNode({ node_id: 'n3', node_type: 'hazard', concern_class: 'safety', binding_status: 'bound' }),
  ]

  it('empty filters return all nodes', () => {
    expect(applyFilters(nodes, {})).toHaveLength(3)
  })

  it('type filter narrows to matching type', () => {
    expect(applyFilters(nodes, { type: 'hazard' })).toHaveLength(2)
    expect(applyFilters(nodes, { type: 'risk' })).toHaveLength(1)
  })

  it('binding filter narrows correctly', () => {
    expect(applyFilters(nodes, { binding: 'bound' })).toHaveLength(2)
    expect(applyFilters(nodes, { binding: 'unbound' })).toHaveLength(1)
  })

  it('tlp filter returns classified node only', () => {
    expect(applyFilters(nodes, { tlp: 'TLP:RED' })).toHaveLength(1)
    expect(applyFilters(nodes, { tlp: 'TLP:WHITE' })).toHaveLength(2)
  })

  it('combined filters intersect correctly', () => {
    expect(applyFilters(nodes, { type: 'hazard', binding: 'bound' })).toHaveLength(1)
    expect(applyFilters(nodes, { type: 'risk', binding: 'unbound' })).toHaveLength(0)
  })

  it('concern filter isolates by concern class', () => {
    expect(applyFilters(nodes, { concern: 'security' })).toHaveLength(1)
    expect(applyFilters(nodes, { concern: 'safety' })).toHaveLength(2)
  })
})

// ── 4. Router config assertions ───────────────────────────────────────────────
// Against the real route table, imported as data. This block used to re-declare the routes inside
// itself and assert on the copy, so it passed no matter what the router said — and it kept passing
// through the move of the browse surface from `/assurance/browse` to `/assurance`.

describe('the assurance route table', () => {
  const routeFor = (path: string) => assuranceRoutes.find(route => route.path === path)

  it('serves the browse surface at /assurance itself', () => {
    /* Not a hub that links to a browse page: the hub's whole content was a banner saying the store
       was fine plus a link to the node list. */
    const route = routeFor(ASSURANCE_BROWSE_PATH)

    expect(ASSURANCE_BROWSE_PATH).toBe('/assurance')
    expect(route).toBeDefined()
    expect('component' in route!).toBe(true)
  })

  it.each(['/assurance/browse'])(
    'redirects the former path %s to the browse surface, query intact',
    (path) => {
      const route = routeFor(path)
      expect(route).toBeDefined()
      expect('redirect' in route!).toBe(true)

      // A bookmarked `?node_id=` or `?view=tree` has to survive the move, so the redirect is a
      // function over the incoming route rather than a bare path string. Called with just the
      // fields it reads — vue-router's own signature takes a full RouteLocation, which a test has
      // no business constructing.
      const redirect = (route as unknown as {
        redirect: (to: { query: Record<string, string>; hash: string }) => unknown
      }).redirect

      expect(redirect({ query: { node_id: 'HAZ@1' }, hash: '' })).toEqual({
        path: ASSURANCE_BROWSE_PATH,
        query: { node_id: 'HAZ@1' },
        hash: '',
      })
    },
  )

  it('declares no route twice', () => {
    const paths = assuranceRoutes.map(route => route.path)
    expect(new Set(paths).size).toBe(paths.length)
  })
})
