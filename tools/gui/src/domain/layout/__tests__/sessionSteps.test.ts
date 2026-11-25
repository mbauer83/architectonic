/**
 * A step is named in the words of the list Save shows (01·6): by what it added to the list, else what it
 * took off it, else what it arranged; and the list falls into what goes to the model and what to the
 * diagram only.
 */
import { describe, expect, it } from 'vitest'
import { byWhatTheyChange, stepName } from '../sessionSteps'

const created = { key: 'create:X', text: 'Create element: X', model: true }
const removed = { key: 'removed:A', text: 'Removed from the diagram: A — it stays in the model' }

describe('the name of a step', () => {
  it('is what it added to the list, the first of several with how many more', () => {
    expect(stepName({ returnedToAutomatic: false, before: [], after: [removed], arranged: ['B'] })).toBe(removed.text)
    expect(stepName({ returnedToAutomatic: false, before: [], after: [removed, created], arranged: [] }))
      .toBe(`${removed.text} and 1 more`)
  })

  it('is what it took off the list, else what it arranged, else returning to automatic', () => {
    expect(stepName({ returnedToAutomatic: false, before: [created], after: [], arranged: [] }))
      .toBe('Take back Create element: X')
    expect(stepName({ returnedToAutomatic: false, before: [created], after: [created], arranged: ['B', 'C'] }))
      .toBe('Arranged: B and 1 more')
    expect(stepName({ returnedToAutomatic: true, before: [], after: [], arranged: ['B'] }))
      .toBe('Return to automatic layout')
  })
})

describe('the list of what Save will write', () => {
  it('falls into what goes to the model and what to this diagram only', () => {
    expect(byWhatTheyChange([removed, created])).toEqual({ model: [created], diagram: [removed] })
  })
})
