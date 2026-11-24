import { describe, expect, it } from 'vitest'
import { hasMoved, modelMoved, movedSentence } from './modelMoved'

const one = (standing: string) => ({ operation: { op: 'edit_entity' }, standing, reason: `${standing} because` })

describe('model moved', () => {
  it('reads drifted and conflicting operations off the served standing, and nothing else', () => {
    const moved = modelMoved([one('applies'), one('drifted'), one('already-there'), one('conflicting'), one('drifted')])

    expect(moved.drifted).toHaveLength(2)
    expect(moved.conflicting).toHaveLength(1)
    expect(hasMoved(moved)).toBe(true)
    expect(movedSentence(moved)).toBe(
      '2 operations changed in the model since they were written. 1 operation no longer has anything to apply to.')
  })

  it('has not moved when every operation applies or is already there', () => {
    const moved = modelMoved([one('applies'), one('already-there')])

    expect(hasMoved(moved)).toBe(false)
    expect(movedSentence(moved)).toBe('')
  })

  it('names one drifted operation in the singular', () => {
    expect(movedSentence(modelMoved([one('drifted')]))).toBe('1 operation changed in the model since it was written.')
  })
})
