import { describe, expect, it } from 'vitest'
import type { CandidateSummary } from '../schemas/candidates'
import { baseChoices, chainOf, defaultBase, descendantsOf, rootOf, stackFrom, stackLine } from './candidateStack'

const candidate = (id: string, parent: string | null = null): CandidateSummary =>
  ({ id, name: `${id} name`, state: 'draft', parent, scope: [], operations: 0 })

// naive ← queue ← bounded; naive ← drift; elsewhere stands alone.
const ALL = [
  candidate('bounded', 'queue'), candidate('queue', 'naive'), candidate('naive'),
  candidate('drift', 'naive'), candidate('elsewhere'),
]

describe('a candidate stack', () => {
  it('walks what a candidate stacks on, nearest first, and stops at a cycle', () => {
    expect(chainOf('bounded', ALL).map((one) => one.id)).toEqual(['bounded', 'queue', 'naive'])
    const cycle = [candidate('a', 'b'), candidate('b', 'a')]
    expect(chainOf('a', cycle).map((one) => one.id)).toEqual(['a', 'b'])
  })

  it('finds what is stacked on a candidate at any depth', () => {
    expect([...descendantsOf('naive', ALL)].sort()).toEqual(['bounded', 'drift', 'queue'])
    expect([...descendantsOf('bounded', ALL)]).toEqual([])
  })

  it('holds a root and what stacks on it, the root first', () => {
    expect(stackFrom('naive', ALL).map((one) => one.id)).toEqual(['naive', 'queue', 'drift', 'bounded'])
    expect(stackFrom('unknown', ALL)).toEqual([])
  })

  it('finds the root a candidate stacks on, which is the candidate itself for one on the model', () => {
    expect(rootOf('bounded', ALL)).toBe('naive')
    expect(rootOf('naive', ALL)).toBe('naive')
    expect(rootOf('unknown', ALL)).toBe('unknown')
  })

  it('says what a candidate stacks on, down to the model', () => {
    expect(stackLine('bounded', ALL)).toBe('stacks on queue name ← naive name ← the current model')
    expect(stackLine('naive', ALL)).toBe('stacks on the current model')
  })

  it('offers as a base the model and every other candidate of the stack not stacked on it', () => {
    const inStack = stackFrom('naive', ALL)
    expect(baseChoices('queue', inStack, ALL).map((one) => one.value)).toEqual(['model', 'naive', 'drift'])
    expect(baseChoices('naive', inStack, ALL).map((one) => one.value)).toEqual(['model'])
  })

  it('compares with the parent by default, and with the model for a candidate on nothing', () => {
    expect(defaultBase('bounded', ALL)).toBe('queue')
    expect(defaultBase('naive', ALL)).toBe('model')
  })
})
