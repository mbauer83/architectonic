import { describe, expect, it } from 'vitest'
import type { CandidateSummary } from '../schemas/candidates'
import { touchingScope } from './touchingScope'

const summary = (id: string, over: Partial<CandidateSummary> = {}): CandidateSummary => ({
  id, name: id, state: 'draft', parent: null, scope: [], diagram: null, operations: 0, ...over,
})

describe('the open candidates a scope touches', () => {
  it('lists a draft or offered candidate reading an element of the scope, by either id spelling', () => {
    const touching = touchingScope(['SRV@1.Abcdef.queue'], [
      summary('CAND@1.a', { scope: ['SRV@1.Abcdef'] }),
      summary('CAND@1.b', { scope: ['SRV@1.Abcdef.queue'], state: 'candidate' }),
      summary('CAND@1.c', { scope: ['SRV@2.Other'] }),
    ])
    expect(touching.map((one) => one.candidate.id)).toEqual(['CAND@1.a', 'CAND@1.b'])
  })

  it('reads what a stacked candidate reads through the stack beneath it', () => {
    const touching = touchingScope(['SRV@1.Abcdef'], [
      summary('root', { scope: ['SRV@1.Abcdef'], state: 'integrated' }),
      summary('top', { parent: 'root' }),
    ])
    expect(touching.map((one) => one.candidate.id)).toEqual(['top'])
  })

  it('leaves out integrated, rejected and superseded candidates, and orders by how much they share', () => {
    const touching = touchingScope(['APP@1.Aaaaaa', 'APP@1.Bbbbbb'], [
      summary('few', { scope: ['APP@1.Aaaaaa'] }),
      summary('many', { scope: ['APP@1.Aaaaaa', 'APP@1.Bbbbbb'] }),
      summary('done', { scope: ['APP@1.Aaaaaa'], state: 'rejected' }),
    ])
    expect(touching.map((one) => [one.candidate.id, one.shared])).toEqual([['many', 2], ['few', 1]])
  })

  it('survives a stack that circles back on itself', () => {
    const touching = touchingScope(['APP@1.Aaaaaa'], [
      summary('x', { parent: 'y', scope: ['APP@1.Aaaaaa'] }), summary('y', { parent: 'x' }),
    ])
    expect(touching.map((one) => one.candidate.id).sort()).toEqual(['x', 'y'])
  })
})
