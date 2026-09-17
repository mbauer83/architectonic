import { describe, expect, it } from 'vitest'
import {
  displayLabelOf,
  displayLabelOverrides,
  drawnLabelFor,
  seededDisplayLabels,
  withDisplayLabel,
  withoutDisplayLabels,
} from './archimateDisplayLabels'

const GOAL = 'GOL@1.aa.provide-governed-read-access'
const ENTITY = { element_label: 'Provide Governed Read Access', name: 'Provide Governed Read Access' }

describe('what the diagram states about an instance', () => {
  it('states nothing until asked to', () => {
    expect(displayLabelOverrides({})).toEqual({})
    expect(displayLabelOf({ occurrence: [] }, GOAL)).toBeUndefined()
  })

  it('keeps only labels that are non-empty strings', () => {
    const de = { display_labels: { [GOAL]: 'Short', 'occ-2': '   ', other: 3 } }

    expect(displayLabelOverrides(de)).toEqual({ [GOAL]: 'Short' })
  })

  it('ignores a list where a mapping belongs rather than failing', () => {
    expect(displayLabelOverrides({ display_labels: ['x'] })).toEqual({})
  })
})

describe('stating and withdrawing a label', () => {
  it('states a trimmed label for the instance and leaves the rest of the data alone', () => {
    const de = withDisplayLabel({ occurrence: [{ id: 'occ-2', backing_entity_id: GOAL }] }, GOAL, '  Short  ')

    expect(de).toEqual({
      occurrence: [{ id: 'occ-2', backing_entity_id: GOAL }],
      display_labels: { [GOAL]: 'Short' },
    })
  })

  it('labels an occurrence independently of the base instance', () => {
    const de = withDisplayLabel(withDisplayLabel({}, GOAL, 'First'), 'occ-2', 'Second')

    expect(displayLabelOf(de, GOAL)).toBe('First')
    expect(displayLabelOf(de, 'occ-2')).toBe('Second')
  })

  it('withdraws with null, and with a blank label, keeping the key so a merge can carry the withdrawal', () => {
    const stated = withDisplayLabel({}, GOAL, 'Short')

    expect(withDisplayLabel(stated, GOAL, null)).toEqual({ display_labels: {} })
    expect(withDisplayLabel(stated, GOAL, '   ')).toEqual({ display_labels: {} })
  })

  it('adds no key when withdrawing from data that never stated a label', () => {
    expect(withDisplayLabel({ occurrence: [] }, GOAL, null)).toEqual({ occurrence: [] })
  })

  it('forgets the statements about instances that are gone and nothing else', () => {
    const de = withDisplayLabel(withDisplayLabel({}, GOAL, 'First'), 'occ-2', 'Second')

    expect(withoutDisplayLabels(de, ['occ-2', 'never-there'])).toEqual({ display_labels: { [GOAL]: 'First' } })
  })

  it('returns the same object when nothing it is asked to forget was stated', () => {
    const de = withDisplayLabel({}, GOAL, 'First')

    expect(withoutDisplayLabels(de, ['occ-2'])).toBe(de)
  })
})

describe('the label a box carries right now', () => {
  it('is the element’s own label when neither the diagram nor the body says otherwise', () => {
    expect(drawnLabelFor({}, {}, GOAL, ENTITY)).toBe('Provide Governed Read Access')
  })

  it('is what a hand-laid body declares when the diagram states nothing', () => {
    expect(drawnLabelFor({}, { [GOAL]: 'Read Access' }, GOAL, ENTITY)).toBe('Read Access')
  })

  it('is the diagram’s statement ahead of both', () => {
    const de = withDisplayLabel({}, GOAL, 'Stated')

    expect(drawnLabelFor(de, { [GOAL]: 'Read Access' }, GOAL, ENTITY)).toBe('Stated')
  })

  it('falls back to the name when the element has no label of its own', () => {
    expect(drawnLabelFor({}, {}, GOAL, { element_label: '', name: 'Named' })).toBe('Named')
  })
})

describe('carrying a hand-laid body’s labels into the diagram’s statement', () => {
  const byId = new Map([[GOAL, ENTITY]])
  const backing = (instanceId: string) => (instanceId === 'occ-2' ? GOAL : instanceId)

  it('carries a label the body declares that the element does not', () => {
    const patch = seededDisplayLabels({}, { [GOAL]: 'Read Access', 'occ-2': 'Again' }, byId, backing)

    expect(patch).toEqual({ display_labels: { [GOAL]: 'Read Access', 'occ-2': 'Again' } })
  })

  it('carries nothing where the body agrees with the element', () => {
    expect(seededDisplayLabels({}, { [GOAL]: 'Provide Governed Read Access' }, byId, backing)).toEqual({})
  })

  it('never overrides what the diagram already states', () => {
    const de = withDisplayLabel({}, GOAL, 'Stated')

    expect(seededDisplayLabels(de, { [GOAL]: 'Read Access' }, byId, backing)).toEqual({})
  })

  it('ignores an instance whose element the diagram no longer holds', () => {
    expect(seededDisplayLabels({}, { 'GOL@9.zz.gone': 'Ghost' }, byId, backing)).toEqual({})
  })
})
