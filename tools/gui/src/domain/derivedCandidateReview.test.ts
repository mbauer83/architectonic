import { describe, expect, it } from 'vitest'
import {
  acceptedConnections, candidateKeyFor, clearDecision, decisionFor, initialCandidateReview, staleAcceptedFindings, withDecision,
} from './derivedCandidateReview'
import type { ConnectionItemSummary } from './schemas/viewpoints'

const conn = (overrides: Partial<ConnectionItemSummary>): ConnectionItemSummary => ({
  id: 'c', type: 'archimate-serving', source: 'a', target: 'b',
  certainty: null, hops: null, via_connection_ids: [], witness_steps: [], ...overrides,
})

describe('initialCandidateReview', () => {
  it('pre-accepts certain candidates and pre-rejects potential ones, ignoring modeled connections', () => {
    const modeled = conn({ id: 'm1' })
    const certain = conn({ id: 'd1', certainty: 'certain', via_connection_ids: ['c1', 'c2'] })
    const potential = conn({ id: 'd2', certainty: 'potential', via_connection_ids: ['c3', 'c4'] })
    const state = initialCandidateReview([modeled, certain, potential])
    expect(decisionFor(state, candidateKeyFor(certain))).toBe('accepted')
    expect(decisionFor(state, candidateKeyFor(potential))).toBe('rejected')
    expect(state.decisions.size).toBe(2)
  })
})

describe('acceptedConnections', () => {
  it('always keeps modeled connections and only accepted derived ones', () => {
    const modeled = conn({ id: 'm1' })
    const certain = conn({ id: 'd1', certainty: 'certain', via_connection_ids: ['c1', 'c2'] })
    const potential = conn({ id: 'd2', certainty: 'potential', via_connection_ids: ['c3', 'c4'] })
    const state = initialCandidateReview([modeled, certain, potential])
    expect(acceptedConnections(state, [modeled, certain, potential])).toEqual([modeled, certain])
  })

  it('reflects an explicit accept of a previously-rejected potential candidate', () => {
    const potential = conn({ id: 'd2', certainty: 'potential', via_connection_ids: ['c3', 'c4'] })
    let state = initialCandidateReview([potential])
    state = withDecision(state, candidateKeyFor(potential), 'accepted')
    expect(acceptedConnections(state, [potential])).toEqual([potential])
  })
})

describe('staleAcceptedFindings', () => {
  it('flags a previously-accepted candidate the fresh result no longer reproduces, carrying its last-known connection', () => {
    const certain = conn({ id: 'd1', certainty: 'certain', via_connection_ids: ['c1', 'c2'] })
    const state = initialCandidateReview([certain])
    expect(staleAcceptedFindings(state, [certain], [])).toEqual([{ key: candidateKeyFor(certain), connection: certain }])
  })

  it('does not flag a rejected candidate as stale, or one the fresh result still reproduces', () => {
    const certain = conn({ id: 'd1', certainty: 'certain', via_connection_ids: ['c1', 'c2'] })
    const potential = conn({ id: 'd2', certainty: 'potential', via_connection_ids: ['c3', 'c4'] })
    const state = initialCandidateReview([certain, potential])
    expect(staleAcceptedFindings(state, [certain, potential], [certain])).toEqual([])
  })
})

describe('clearDecision', () => {
  it('removes one key without touching any other decision', () => {
    const certain = conn({ id: 'd1', certainty: 'certain', via_connection_ids: ['c1', 'c2'] })
    const potential = conn({ id: 'd2', certainty: 'potential', via_connection_ids: ['c3', 'c4'] })
    const state = initialCandidateReview([certain, potential])
    const cleared = clearDecision(state, candidateKeyFor(certain))
    expect(decisionFor(cleared, candidateKeyFor(certain))).toBeUndefined()
    expect(decisionFor(cleared, candidateKeyFor(potential))).toBe('rejected')
  })
})
