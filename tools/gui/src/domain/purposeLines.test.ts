import { describe, expect, it } from 'vitest'
import { purposeEntries, purposeSentence, statesPurpose, withEntry, withoutEntry } from './purposeLines'
import { definitionFromMapping, definitionToMapping } from './viewpointDefinitionSerialization'

describe('purpose entries', () => {
  it('reads prose and references, and drops what is neither', () => {
    expect(purposeEntries(['Operations', { ref: 'STK@1.a' }, 7, { name: 'x' }, null])).toEqual([
      'Operations', { ref: 'STK@1.a' },
    ])
    expect(purposeEntries(undefined)).toEqual([])
  })

  it('adds an entry once, and never empty prose', () => {
    const entries = withEntry(['Operations'], { ref: 'STK@1.a' })

    expect(entries).toEqual(['Operations', { ref: 'STK@1.a' }])
    expect(withEntry(entries, { ref: 'STK@1.a' })).toEqual(entries)
    expect(withEntry(entries, ' Operations ')).toEqual(entries)
    expect(withEntry(entries, '   ')).toEqual(entries)
    expect(withoutEntry(entries, 0)).toEqual([{ ref: 'STK@1.a' }])
  })

  it('keeps a viewpoint\'s references through the editor\'s read and write', () => {
    const mapping = { slug: 'probe', stakeholders: ['Architects', { ref: 'STK@1.a' }], concerns: [{ ref: 'GOL@1.b' }] }

    const written = definitionToMapping(definitionFromMapping(mapping))

    expect(written.stakeholders).toEqual(['Architects', { ref: 'STK@1.a' }])
    expect(written.concerns).toEqual([{ ref: 'GOL@1.b' }])
  })
})

describe('the shown line', () => {
  it('says who a diagram is for and what it answers', () => {
    const purpose = {
      stakeholders: [{ text: 'Operations', ref: 'STK@1.a' }, { text: 'Warehouse' }],
      concerns: [{ text: 'How fast?' }],
    }

    expect(statesPurpose(purpose)).toBe(true)
    expect(purposeSentence(purpose)).toBe('For Operations, Warehouse · Answers How fast?')
    expect(purposeSentence({ stakeholders: [], concerns: [{ text: 'Cost' }] })).toBe('Answers Cost')
  })

  it('states nothing where neither list holds an entry', () => {
    expect(statesPurpose(undefined)).toBe(false)
    expect(statesPurpose({ stakeholders: [], concerns: [] })).toBe(false)
  })
})
