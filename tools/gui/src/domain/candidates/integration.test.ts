/**
 * The Integration tab's reading of a conflict: what each party proposes, the resolution each action makes,
 * what a party answers in the analysis, and the draft a raised decision opens with.
 */
import { describe, expect, it } from 'vitest'
import type { DocumentTableRow, IntegrationConflict } from '../schemas/candidates'
import {
  answerLinks, conflictTitle, decisionDraft, mergedResolution, partyResolution, permits, proposal, resolutionWords,
} from './integration'

const conflict: IntegrationConflict = {
  kind: 'same-key', subject: 'name of SRV@1.svc', actions: ['take', 'drop', 'merge'],
  parties: [
    { set_id: 'CAND@1.queues', operation: { op: 'edit_entity', artifact_id: 'SRV@1.svc', field: 'name', value: 'Queue' } },
    { set_id: 'CAND@1.gate', operation: { op: 'edit_entity', artifact_id: 'SRV@1.svc', field: 'name', value: 'Gate' } },
  ],
}
const row = (id: string, values: Record<string, string | readonly string[]>): DocumentTableRow =>
  ({ row_id: id, values }) as unknown as DocumentTableRow

describe('a conflict between candidates being integrated', () => {
  it('says what it is about and what each party proposes', () => {
    const nameOf = (id: string) => (id === 'SRV@1.svc' ? 'Promotion Service' : id)
    expect(conflictTitle(conflict, nameOf)).toBe('Both change the name of Promotion Service')
    expect(proposal(conflict.parties[0].operation, nameOf)).toBe('Set name of Promotion Service to “Queue”')
    expect(permits(conflict, 'merge')).toBe(true)
  })

  it('makes the resolution each action asks for, by kind and subject', () => {
    expect(partyResolution(conflict, 'take', 'CAND@1.gate'))
      .toEqual({ kind: 'same-key', subject: 'name of SRV@1.svc', action: 'take', party: 'CAND@1.gate' })
    expect(mergedResolution(conflict, 'Queue Gate'))
      .toEqual({ kind: 'same-key', subject: 'name of SRV@1.svc', action: 'merge', value: 'Queue Gate' })
    expect(resolutionWords(partyResolution(conflict, 'drop', 'CAND@1.gate'), () => 'Gate', 'the name of Service'))
      .toBe('Dropped the change of Gate to the name of Service')
  })

  it('links a party to its adaptation row, the end states it answers and their stressors', () => {
    const adaptations = [row('A1', { candidate_architecture: 'CAND@1.queues.bounded-queues', end_states: ['E1'] })]
    const stressors = [row('S1', { end_state: 'E1' }), row('S2', { end_state: 'E2' })]

    expect(answerLinks('CAND@1.queues', adaptations, stressors))
      .toEqual({ adaptations: ['A1'], endStates: ['E1'], stressors: ['S1'] })
  })

  it('drafts a decision with each side as an option and nothing decided', () => {
    const draft = decisionDraft(conflict, [
      { name: 'Queues', proposes: 'Set name to “Queue”', answers: ['Promotions stall'] },
      { name: 'Gate', proposes: 'Set name to “Gate”', answers: [] },
    ], (id) => (id === 'SRV@1.svc' ? 'Promotion Service' : id))

    expect(draft.title).toBe('Decide the name of Promotion Service')
    expect(draft.body).toContain('## Context')
    expect(draft.body).toContain('- **Queues**: Set name to “Queue” (answers Promotions stall)')
    expect(draft.body).toContain('To be decided.')
  })
})
