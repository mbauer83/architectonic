import { describe, expect, it } from 'vitest'
import { moveSentence, targetOperationLines, targetSentence, targetStateOf } from './candidateTargetState'

describe('targetStateOf', () => {
  it('reads the target state a candidate record holds, with empty mappings left out', () => {
    expect(targetStateOf({ 'target-state': { baseline: 'PLT@1.a', target: 'PLT@1.b', gap: 'ASS@1.c' } }))
      .toEqual({ baseline: 'PLT@1.a', target: 'PLT@1.b', gap: 'ASS@1.c', copies: {}, added: {} })
  })

  it('reads none where the record holds none, or holds something else', () => {
    expect(targetStateOf({ id: 'CAND@1.a' })).toBeNull()
    expect(targetStateOf({ 'target-state': { baseline: 3 } })).toBeNull()
  })
})

describe('the confirmation sentences', () => {
  it('say what applying as a target state writes, and that the originals stay', () => {
    const sentence = targetSentence({
      baseline: 'b', target: 't', gap: 'g', copies: { a: 'c' }, added: { x: 'y', z: 'w' },
    }, 12)
    expect(sentence).toBe(
      'Writes 12 operations beside the baseline in one write: 2 added elements as drafts, 1 "(target)" copy of '
      + 'what it changes, a Baseline and a Target plateau with a gap between them. The elements it changes stay '
      + 'as they are until it is moved into the baseline.',
    )
  })

  it('say what moving into the baseline writes', () => {
    expect(moveSentence(1)).toContain('Writes 1 operation in one write')
  })
})

describe('targetOperationLines', () => {
  it('names an element by what the operations create it as, or by its part in the target state', () => {
    const lines = targetOperationLines([
      { op: 'create_entity', ref: 'r1', artifact_id: 'APP@1.a.cache', fields: { name: 'Cache' } },
      { op: 'add_connection', source_entity: 'APP@1.a', connection_type: 'archimate-serving', target_entity: 'APP@1.b' },
      { op: 'remove_entity', artifact_id: 'PLT@2.t' },
    ], { baseline: 'PLT@2.b.base', target: 'PLT@2.t.target', gap: 'ASS@2.g.gap', copies: {}, added: {} })
    expect(lines).toEqual([
      'Create Cache', 'Connect Cache → APP@1.b (archimate-serving)', 'Remove the Target plateau',
    ])
  })
})
