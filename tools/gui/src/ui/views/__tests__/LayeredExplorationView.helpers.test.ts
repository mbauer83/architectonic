import { describe, expect, it } from 'vitest'
import { buildRenderGraph, derivedCandidates, PRESET_DEFAULTS } from '../LayeredExplorationView.helpers'
import { initialCandidateReview, withDecision, candidateKeyFor } from '../../../domain/derivedCandidateReview'
import type { ConnectionItemSummary, EntityItemSummary } from '../../../domain'

const entity = (id: string): EntityItemSummary => ({
  id, name: `Name ${id}`, type: 'business-process', specialization_slugs: [], group: 'g', domain: 'application', membership: 'primary',
  status: 'draft', version: '1', column_values: null, anchor_modeled_distance: null, matched_via_derived_hops: null,
})
const conn = (overrides: Partial<ConnectionItemSummary>): ConnectionItemSummary => ({
  id: 'c', type: 'archimate-serving', source: 'a', target: 'b', certainty: null, hops: null, via_connection_ids: [], witness_steps: [], ...overrides,
})

describe('buildRenderGraph', () => {
  it('renders every entity as a node and every non-rejected connection as an edge', () => {
    const modeled = conn({ id: 'm1', source: 'a', target: 'b' })
    const potential = conn({ id: 'd1', source: 'a', target: 'c', certainty: 'potential', via_connection_ids: ['x'] })
    const review = initialCandidateReview([modeled, potential])
    const graph = buildRenderGraph([entity('a'), entity('b'), entity('c')], [modeled, potential], review)
    expect(graph.nodes.map((n) => n.id)).toEqual(['a', 'b', 'c'])
    expect(graph.edges).toEqual([{ source: 'a', target: 'b', connType: 'archimate-serving', certainty: null }])
  })

  it('includes a derived edge once the user accepts it', () => {
    const potential = conn({ id: 'd1', source: 'a', target: 'c', certainty: 'potential', via_connection_ids: ['x'] })
    let review = initialCandidateReview([potential])
    review = withDecision(review, candidateKeyFor(potential), 'accepted')
    const graph = buildRenderGraph([entity('a'), entity('c')], [potential], review)
    expect(graph.edges).toHaveLength(1)
  })
})

describe('derivedCandidates', () => {
  it('returns only connections with a non-null certainty', () => {
    const modeled = conn({ id: 'm1' })
    const derived = conn({ id: 'd1', certainty: 'certain', via_connection_ids: ['x'] })
    expect(derivedCandidates([modeled, derived])).toEqual([derived])
  })
})

describe('PRESET_DEFAULTS', () => {
  it('gives layered and motivation-support presets distinct labels and neighbor criteria', () => {
    expect(PRESET_DEFAULTS.layered.label).not.toBe(PRESET_DEFAULTS['motivation-support'].label)
    const layeredCriteria = PRESET_DEFAULTS.layered.neighborCriteria()
    const motivationCriteria = PRESET_DEFAULTS['motivation-support'].neighborCriteria()
    expect(layeredCriteria.children).not.toEqual(motivationCriteria.children)
  })
})
