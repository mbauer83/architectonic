/**
 * A drop is said in words (03·9–10, Q13): a box that takes the element and an element that may hold it
 * are named as what the drop does; one that refuses says why in one line; a box that draws it by its rule
 * anyway, and an element whose answer is still awaited, say nothing.
 */
import { describe, expect, it } from 'vitest'
import { dropVerdict } from '../dropVerdict'
import { sideInBand } from '../edgeBand'

const words = (type: string) => type.replace(/-/g, ' ')
const fn = { name: 'Detect Accepted Changes', type: 'application-function', domain: 'common' }
const object = { name: 'Proposed Change', type: 'business-object', domain: 'business' }

describe('dropping an element on a box', () => {
  it('into a grouping of the diagram that takes anything', () => {
    expect(dropVerdict(fn, { kind: 'box', name: 'Team A', ruled: false, admits: { kind: 'anything' } }, words))
      .toEqual({ kind: 'into', words: 'Into Team A' })
  })

  it('refused by a box whose rule admits another layer, saying why in one line', () => {
    const business = {
      kind: 'box', name: 'Business', ruled: true, admits: { kind: 'domain', domain: 'business' },
    } as const
    expect(dropVerdict(fn, business, words)).toEqual({
      kind: 'refused',
      why: 'Business holds business elements only; Detect Accepted Changes is an application function (common).',
    })
    // A box drawing it by its rule anyway changes nothing, so nothing is said.
    expect(dropVerdict(object, business, words)).toBeNull()
  })
})

describe('dropping an element on an element', () => {
  const container = { kind: 'element', name: 'Repository Promotion Service', type: 'application-service' } as const

  it('offers to nest it where the ontology permits a containment relationship', () => {
    expect(dropVerdict(fn, { ...container, holds: ['archimate-aggregation'] }, words))
      .toEqual({ kind: 'nest', words: 'Nest in Repository Promotion Service…' })
  })

  it('refuses it where none is permitted, and waits while the answer is not known', () => {
    expect(dropVerdict(fn, { ...container, holds: [] }, words)).toEqual({
      kind: 'refused',
      why: 'Repository Promotion Service cannot hold Detect Accepted Changes: the ontology permits no part-of '
        + 'relationship from an application service to an application function.',
    })
    expect(dropVerdict(fn, container, words)).toBeNull()
  })
})

describe('the edge band of an element', () => {
  const extent = { left: 0, top: 0, right: 100, bottom: 40 }

  it('is the nearest side within the band, and nothing deeper inside or outside', () => {
    expect(sideInBand(extent, { x: 2, y: 20 })).toBe('left')
    expect(sideInBand(extent, { x: 50, y: 38 })).toBe('bottom')
    expect(sideInBand(extent, { x: 50, y: 20 })).toBeNull()
    expect(sideInBand(extent, { x: -1, y: 20 })).toBeNull()
  })
})
