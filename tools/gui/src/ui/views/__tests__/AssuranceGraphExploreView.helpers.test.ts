/**
 * Assurance graph panel-state logic: typed fetch outcomes, the locked store
 * collapsing the entire panel (selection, notices, and the graph itself), and
 * the truncation notice for partial size-budget results.
 */
import { describe, it, expect } from 'vitest'
import {
  assuranceBandPlacement, clearsGraph, emptyPanelState, nodeTypeLabel, outcomeForResponse,
  panelStateForOutcome, truncationNotice,
  type AssuranceNeighborsResponse,
} from '../AssuranceGraphExploreView.helpers'

const response = (overrides: Partial<AssuranceNeighborsResponse> = {}): AssuranceNeighborsResponse => ({
  root_id: 'HAZ@1',
  nodes: [],
  edges: [],
  truncated: false,
  frontier_node_ids: [],
  visibility_limited: false,
  ...overrides,
})

describe('outcomeForResponse', () => {
  it('maps the status matrix to typed outcomes', () => {
    expect(outcomeForResponse(200, response()).kind).toBe('graph')
    expect(outcomeForResponse(423, null).kind).toBe('locked')
    expect(outcomeForResponse(404, null).kind).toBe('not_found')
    expect(outcomeForResponse(503, { retryable: true, message: 'over budget' }))
      .toEqual({ kind: 'retryable', message: 'over budget' })
    expect(outcomeForResponse(500, null).kind).toBe('error')
  })
})

describe('locked store collapses the panel', () => {
  it('clears selection and every notice, and demands the graph be discarded', () => {
    const busy = {
      selectedNodeId: 'HAZ@1',
      lockedMessage: null,
      errorMessage: 'old error',
      retryable: true,
      truncationNotice: 'Partial result…',
    }
    const outcome = outcomeForResponse(423, null)
    const next = panelStateForOutcome(outcome, busy)
    expect(next.selectedNodeId).toBeNull()
    expect(next.errorMessage).toBeNull()
    expect(next.truncationNotice).toBeNull()
    expect(next.lockedMessage).toContain('locked')
    expect(clearsGraph(outcome)).toBe(true)
  })

  it('only the locked outcome clears the graph', () => {
    expect(clearsGraph(outcomeForResponse(404, null))).toBe(false)
    expect(clearsGraph(outcomeForResponse(503, null))).toBe(false)
    expect(clearsGraph(outcomeForResponse(200, response()))).toBe(false)
  })
})

describe('successful fetch', () => {
  it('keeps the selection and resets stale errors', () => {
    const prev = { ...emptyPanelState(), selectedNodeId: 'HAZ@1', errorMessage: 'stale' }
    const next = panelStateForOutcome(outcomeForResponse(200, response()), prev)
    expect(next.selectedNodeId).toBe('HAZ@1')
    expect(next.errorMessage).toBeNull()
    expect(next.truncationNotice).toBeNull()
  })
})

describe('truncationNotice', () => {
  it('is silent for complete results', () => {
    expect(truncationNotice(response())).toBeNull()
  })

  it('names the frontier when a size budget cut the result', () => {
    const notice = truncationNotice(response({ truncated: true, frontier_node_ids: ['HAZ@1'] }))
    expect(notice).toContain('size budget')
    expect(notice).toContain('1 cut short')
  })
})

describe('nodeTypeLabel', () => {
  it('uses the id prefix as the in-shape label', () => {
    expect(nodeTypeLabel('HAZ@x1')).toBe('HAZ')
  })
})

describe('assuranceBandPlacement', () => {
  it('orders the STPA chain from what must not happen down to how it could', () => {
    const band = (nodeType: string): number => assuranceBandPlacement(nodeType).band

    expect(band('loss')).toBeLessThan(band('hazard'))
    expect(band('hazard')).toBeLessThan(band('unsafe-control-action'))
    expect(band('unsafe-control-action')).toBeLessThan(band('loss-scenario'))
  })

  it('keeps every chain step in the stack rather than off to a side', () => {
    for (const nodeType of ['loss', 'hazard', 'unsafe-control-action', 'loss-scenario']) {
      expect(assuranceBandPlacement(nodeType).side, nodeType).toBeNull()
    }
  })

  it('lifts risk and the assurance argument out of the chain, level with its middle', () => {
    // They grade or argue about what the chain found rather than being steps of it, so
    // stacking them would assert a place in a sequence they are not part of.
    const chainBands = ['loss', 'hazard', 'unsafe-control-action', 'loss-scenario']
      .map((t) => assuranceBandPlacement(t).band)

    for (const nodeType of ['risk', 'obligation', 'evidence']) {
      const placement = assuranceBandPlacement(nodeType)
      expect(placement.side, nodeType).not.toBeNull()
      expect(placement.band).toBeGreaterThan(Math.min(...chainBands))
      expect(placement.band).toBeLessThan(Math.max(...chainBands))
    }
  })

  it('places an unrecognised type at the bottom rather than dropping it', () => {
    // A build that has not heard of a node type must still put it somewhere visible.
    const placement = assuranceBandPlacement('some-future-node-type')

    expect(placement.side).toBeNull()
    expect(placement.band).toBeGreaterThan(assuranceBandPlacement('loss-scenario').band)
  })
})
