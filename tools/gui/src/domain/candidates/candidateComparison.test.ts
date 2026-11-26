import { describe, expect, it } from 'vitest'
import type { ChangeDifference, CandidateSummary } from '../schemas/candidates'
import { diffMarks } from './elementMarks'
import { changedByOthers, commonBase, comparedIds, sharedBases, withOthers } from './candidateComparison'

const candidate = (id: string, parent: string | null = null): CandidateSummary =>
  ({ id, name: `${id} name`, state: 'draft', parent, scope: [], diagram: null, operations: 0 })

// naive ← queue ← bounded; naive ← queue ← retry; naive ← drift; elsewhere stands alone.
const ALL = [
  candidate('naive'), candidate('queue', 'naive'), candidate('bounded', 'queue'), candidate('retry', 'queue'),
  candidate('drift', 'naive'), candidate('elsewhere'),
]

const changed = (target: string, change = 'edited'): ChangeDifference =>
  ({ kind: 'entity', target, change, fields: change === 'edited' ? { name: { before: 'a', after: 'b' } } : {} })

describe('comparing candidate architectures', () => {
  it('reads the compared candidates from an address once each, in order, ignoring what is not an id', () => {
    expect(comparedIds(['b', 'a', 'b', '', null, 3])).toEqual(['b', 'a'])
  })

  it('offers the model and every candidate all of them stack on, from the model upwards', () => {
    expect(sharedBases(['bounded', 'retry'], ALL).map((one) => one.value)).toEqual(['model', 'naive', 'queue'])
    expect(sharedBases(['bounded', 'drift'], ALL).map((one) => one.value)).toEqual(['model', 'naive'])
    expect(sharedBases(['bounded', 'elsewhere'], ALL).map((one) => one.value)).toEqual(['model'])
  })

  it('never offers one of the compared candidates as the base of the others', () => {
    expect(sharedBases(['queue', 'bounded'], ALL).map((one) => one.value)).toEqual(['model', 'naive'])
  })

  it('reads against the nearest shared base unless a base all of them share is asked for', () => {
    expect(commonBase(['bounded', 'retry'], ALL)).toBe('queue')
    expect(commonBase(['bounded', 'retry'], ALL, 'naive')).toBe('naive')
    expect(commonBase(['bounded', 'drift'], ALL, 'queue')).toBe('naive')
    expect(commonBase(['bounded', 'elsewhere'], ALL)).toBe('model')
    expect(commonBase([], ALL)).toBe('model')
  })

  it('pairs each candidate with the elements another compared candidate changes as well', () => {
    const others = changedByOthers([
      { id: 'a', diff: [changed('ENT@1.x.db'), changed('ENT@2.y.api')] },
      { id: 'b', diff: [changed('ENT@1.x.db', 'removed')] },
      { id: 'c', diff: [changed('ENT@1.x.db', 'added'), changed('ENT@2.y.api')] },
    ])
    expect(Object.fromEntries(others.get('a') ?? [])).toEqual({ 'ENT@1.x': ['b', 'c'], 'ENT@2.y': ['c'] })
    expect(Object.fromEntries(others.get('b') ?? [])).toEqual({ 'ENT@1.x': ['a', 'c'] })
  })

  it('does not pair a changed relation, whose ends are not marked', () => {
    const relation: ChangeDifference = {
      kind: 'connection', change: 'added', fields: {},
      target: { source_entity: 'ENT@1.x.db', connection_type: 'archimate-serving', target_entity: 'ENT@2.y.api' },
    }
    expect(changedByOthers([{ id: 'a', diff: [relation] }, { id: 'b', diff: [relation] }]).get('a')?.size).toBe(0)
  })

  it('says on a mark which other candidates change the same element, and leaves the rest alone', () => {
    const marks = diffMarks({
      diff: [changed('ENT@1.x.db'), changed('ENT@2.y.api', 'added')], view: { entities: [], connections: [] },
    })
    const told = withOthers(marks, new Map([['ENT@1.x', ['b']]]), (id) => `${id} name`)
    expect(told.get('ENT@1.x')?.title).toContain('also changed in b name')
    expect(told.get('ENT@1.x')?.tag).toBe('~')
    expect(told.get('ENT@2.y')).toEqual(marks.get('ENT@2.y'))
  })
})
