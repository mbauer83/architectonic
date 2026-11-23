import { describe, expect, it } from 'vitest'
import type { AddressedReading, ReadingRelation } from './diagramReading'
import { REACH_STEPS, reachOf, readingFromQuery, readingQuery, resolveFocus } from './diagramReading'

const rel = (id: string, source: string, target: string, directed = true): ReadingRelation =>
  ({ id, source, target, directed })

// a → b → c → d, and e — f undirected, f → b
const relations = [rel('ab', 'a', 'b'), rel('bc', 'b', 'c'), rel('cd', 'c', 'd'), rel('ef', 'e', 'f', false), rel('fb', 'f', 'b')]

describe('the reach of a selection', () => {
  it('follows outgoing relations in their model direction, one step at a time', () => {
    expect(reachOf(['b'], relations, { incoming: 0, outgoing: 1 }).outgoing).toEqual(['c'])
    expect(reachOf(['b'], relations, { incoming: 0, outgoing: 2 }).outgoing).toEqual(['c', 'd'])
    expect(reachOf(['b'], relations, { incoming: 0, outgoing: 'all' }).outgoing).toEqual(['c', 'd'])
  })

  it('follows incoming relations against it, and an undirected relation either way', () => {
    const reached = reachOf(['b'], relations, { incoming: 'all', outgoing: 0 })
    expect(reached.incoming).toEqual(['a', 'f', 'e'])
    expect(reached.outgoing).toEqual([])
    expect(reachOf(['e'], relations, { incoming: 0, outgoing: 1 }).outgoing).toEqual(['f'])
    expect(reachOf(['f'], relations, { incoming: 1, outgoing: 0 }).incoming).toEqual(['e'])
  })

  it('keeps at full strength exactly the relations a walk crossed', () => {
    expect([...reachOf(['b'], relations, { incoming: 1, outgoing: 1 }).relations].sort()).toEqual(['ab', 'bc', 'fb'])
    expect(reachOf(['b'], relations, { incoming: 0, outgoing: 0 }).relations.size).toBe(0)
  })

  it('never lists the selection itself, and stops on a cycle', () => {
    const cycle = [rel('xy', 'x', 'y'), rel('yx', 'y', 'x')]
    expect(reachOf(['x'], cycle, { incoming: 'all', outgoing: 'all' })).toMatchObject({ incoming: ['y'], outgoing: ['y'] })
    expect(reachOf(['a', 'b'], relations, { incoming: 0, outgoing: 1 }).outgoing).toEqual(['c'])
  })
})

describe('the reading in the address', () => {
  const stem = 'BOB@1712870400.so7gfN'
  const other = 'ACT@1712870400.Nn7Oo7'

  it('reads back every reading it writes — every step either way, a view and none', () => {
    for (const incoming of REACH_STEPS) {
      for (const outgoing of REACH_STEPS) {
        for (const view of [null, { x: 908, y: -263, percent: 48 }]) {
          const reading: AddressedReading = { focus: [stem, other], reach: { incoming, outgoing }, view }
          expect(readingFromQuery(readingQuery(reading))).toEqual(reading)
        }
      }
    }
  })

  it('writes stems, so a link outlives a rename', () => {
    const query = readingQuery({ focus: [`${stem}.engagement-repository`], reach: { incoming: 1, outgoing: 'all' }, view: null })
    expect(query).toEqual({ focus: stem, reach: 'in:1,out:all' })
  })

  it('writes no focus and no reach for an empty selection, and keeps the window', () => {
    expect(readingQuery({ focus: [], reach: { incoming: 2, outgoing: 2 }, view: { x: 1.4, y: 2.6, percent: 99.5 } }))
      .toEqual({ view: '1,3,100' })
  })

  it('leaves at its default a part it cannot read, rather than refusing the reading', () => {
    expect(readingFromQuery({ focus: `${stem},,`, reach: 'in:7,out:2', view: '1,2' })).toEqual({
      focus: [stem], reach: { incoming: 1, outgoing: 2 }, view: null,
    })
    expect(readingFromQuery({ reach: 'sideways', view: '1,2,0' })).toEqual({
      focus: [], reach: { incoming: 1, outgoing: 1 }, view: null,
    })
    expect(readingFromQuery({ focus: [stem, other] }).focus).toEqual([stem])
  })

  it('resolves stems against what the diagram draws, in the address order, dropping what it does not', () => {
    const drawn = [`${other}.architect`, `${stem}.engagement-repository`]
    expect(resolveFocus([stem, 'XYZ@1.gone', `${other}.renamed`], drawn)).toEqual([drawn[1], drawn[0]])
  })
})
