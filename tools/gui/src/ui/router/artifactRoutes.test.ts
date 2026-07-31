import { describe, expect, it } from 'vitest'
import {
  ROUTE_TEMPLATES,
  UnaddressableIdentityError,
  assuranceAnalysisCreateRoute,
  assuranceAnalysisDiagramRoute,
  assuranceAnalysisMethodRoute,
  assuranceNodeDetailRoute,
  assuranceVulnerabilityRoute,
  diagramDetailRoute,
  diagramEditRoute,
  encodeIdentitySegment,
  entityDetailRoute,
  entityGraphRoute,
  viewpointMatrixRoute,
} from './artifactRoutes'

describe('encodeIdentitySegment', () => {
  it('escapes the fragment marker, without which a diagram-local id loses its tail', () => {
    // `DATATY@….x#Order` is one identity. Unescaped, the browser treats `#Order` as a fragment
    // and never sends it, so the server sees a request for the host diagram instead.
    expect(encodeIdentitySegment('DATATY@1782085920.9Nrbqf.model#Order')).toBe(
      'DATATY%401782085920.9Nrbqf.model%23Order',
    )
  })

  it('leaves the dot alone, because the server decodes %2E back to it', () => {
    // Encoding it would produce a second spelling of one identity — different cache keys, same
    // resource.
    expect(encodeIdentitySegment('APP@1712870400.abc123.thing')).toContain('.abc123.thing')
    expect(encodeIdentitySegment('APP@1712870400.abc123.thing')).not.toContain('%2E')
  })

  it('escapes a slash, which the server then rejects as outside the identifier grammar', () => {
    expect(encodeIdentitySegment('pkg:npm/left-pad@1.3.0')).toContain('%2F')
  })
})

describe('canonical route builders', () => {
  it('addresses an entity and its neighbourhood by path', () => {
    expect(entityDetailRoute('APP@1.ab.thing')).toBe('/entities/APP%401.ab.thing')
    expect(entityGraphRoute('APP@1.ab.thing')).toBe('/entities/APP%401.ab.thing/graph')
  })

  it('addresses a diagram and its edit surface by path', () => {
    expect(diagramDetailRoute('CC@1.xy.map')).toBe('/diagrams/CC%401.xy.map')
    expect(diagramEditRoute('CC@1.xy.map')).toBe('/diagrams/CC%401.xy.map/edit')
  })

  it('addresses a viewpoint projection by the viewpoint slug', () => {
    expect(viewpointMatrixRoute('capability-map')).toBe('/viewpoints/capability-map/matrix')
  })

  it('addresses an assurance node and an analysis method surface by path', () => {
    expect(assuranceNodeDetailRoute('AN@1.pq')).toBe('/assurance/nodes/AN%401.pq')
    expect(assuranceAnalysisMethodRoute('ANL@1.rs', 'fmea')).toBe('/assurance/analyses/ANL%401.rs/fmea')
  })

  it('separates creating an analysis from resuming one', () => {
    expect(assuranceAnalysisCreateRoute('stpa')).toBe('/assurance/analyses/new/stpa')
  })

  it('refuses to spell an identity that a collection route already claims', () => {
    // Without this, the builder would emit the create surface's URL for an analysis whose id
    // happened to be `new`, and the resulting link would resolve to a different page than the
    // caller asked for.
    expect(() => assuranceAnalysisMethodRoute('new', 'stpa')).toThrow(UnaddressableIdentityError)
    expect(() => entityDetailRoute('groups')).toThrow(UnaddressableIdentityError)
  })

  it('addresses an assurance projection by analysis and type together', () => {
    // One control structure per STPA and one matrix per FMEA: the type alone names no drawing.
    expect(assuranceAnalysisDiagramRoute('ANL@1.rs', 'fmea-matrix')).toBe(
      '/assurance/analyses/ANL%401.rs/diagrams/fmea-matrix',
    )
  })

  it('addresses a vulnerability by its canonical identifier', () => {
    expect(assuranceVulnerabilityRoute('CVE-2024-1234')).toBe('/assurance/vulnerabilities/CVE-2024-1234')
  })
})

describe('route templates', () => {
  it('never spells a collection in the singular', () => {
    const singular = Object.values(ROUTE_TEMPLATES).filter((template) =>
      /^\/(entity|document|diagram|matrix|viewpoint)(\/|$)/.test(template),
    )
    expect(singular).toEqual([])
  })

  it('puts identity in a path segment, never a query string', () => {
    expect(Object.values(ROUTE_TEMPLATES).filter((t) => t.includes('?'))).toEqual([])
  })
})
