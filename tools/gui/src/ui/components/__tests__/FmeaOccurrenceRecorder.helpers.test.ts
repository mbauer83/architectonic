import { describe, expect, it } from 'vitest'
import {
  citedFacts,
  factorRequestBody,
  initialDraft,
  isSubmittable,
  recorderErrorMessage,
} from '../FmeaOccurrenceRecorder.helpers'
import { OCCURRENCE_SCALE_SAMPLE, cellAwaitingOccurrence } from './fmeaCellFixtures'

describe('initialDraft', () => {
  it('seeds the rationale from the cited facts and leaves the value empty', () => {
    const draft = initialDraft(cellAwaitingOccurrence(), 'analyst')

    expect(draft.justification).toContain('nothing can stand in for it')
    expect(draft.value).toBe('')
  })

  it('offers no member of the scale as a starting value', () => {
    const draft = initialDraft(cellAwaitingOccurrence(), 'analyst')

    expect(OCCURRENCE_SCALE_SAMPLE).not.toContain(draft.value)
  })

  it('carries the remembered author through so it is typed once', () => {
    expect(initialDraft(cellAwaitingOccurrence(), 'analyst').author).toBe('analyst')
  })
})

describe('citedFacts', () => {
  it('splits the drafted rationale into the facts it was built from', () => {
    expect(citedFacts('- one thing\n- another thing')).toEqual(['one thing', 'another thing'])
  })

  it('is empty when the model knew nothing to cite', () => {
    expect(citedFacts('')).toEqual([])
  })
})

describe('isSubmittable', () => {
  const complete = { value: 'occasional', justification: 'because of the above', author: 'analyst' }

  it('accepts a judgement with a value, a rationale and someone accountable', () => {
    expect(isSubmittable(complete)).toBe(true)
  })

  it('refuses a value with no stated reason', () => {
    expect(isSubmittable({ ...complete, justification: '   ' })).toBe(false)
  })

  it('refuses an unattributed judgement', () => {
    expect(isSubmittable({ ...complete, author: '' })).toBe(false)
  })

  it('refuses a rationale with no value chosen', () => {
    expect(isSubmittable({ ...complete, value: '' })).toBe(false)
  })
})

describe('factorRequestBody', () => {
  it('files the judgement against the basis digest of the cell it was opened from', () => {
    const body = factorRequestBody(cellAwaitingOccurrence(), {
      value: 'occasional', justification: 'stated', author: ' analyst ',
    })

    // No `node_id`: the failure mode is the address the judgement is posted to.
    expect(body).toEqual({
      factor: 'occurrence',
      value: 'occasional',
      justification: 'stated',
      author: 'analyst',
      basis_digest: 'occ-1',
    })
  })

  it('never sends an empty digest for a cell that has one', () => {
    expect(factorRequestBody(cellAwaitingOccurrence(), {
      value: 'rare', justification: 'stated', author: 'analyst',
    }).basis_digest).not.toBe('')
  })
})

describe('recorderErrorMessage', () => {
  it('names a locked store as a state to act on, not a failure', () => {
    expect(recorderErrorMessage(423, null)).toContain('locked')
  })

  it("prefers the backend's own field messages over a restatement", () => {
    const message = recorderErrorMessage(422, {
      errors: [{ message: 'a basis digest is required' }, { message: 'a rationale is required' }],
    })

    expect(message).toBe('a basis digest is required; a rationale is required')
  })

  it('still says something when the response carried no detail', () => {
    expect(recorderErrorMessage(500, null)).toBe('The judgement was not recorded.')
  })
})
