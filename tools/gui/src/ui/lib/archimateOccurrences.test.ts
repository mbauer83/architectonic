import { describe, it, expect } from 'vitest'
import {
  addOccurrence,
  drawingKey,
  occurrenceOrdinal,
  occurrencesOf,
  removeOccurrence,
} from './archimateOccurrences'

const ENTITY = { artifact_id: 'BOB@1.aa.repo', display_alias: 'BOB_REPO', name: 'Repository' }

describe('identifying one drawing of an entity', () => {
  it('tells the base drawing from an occurrence', () => {
    // Rows are per drawing, so expansion state keyed by entity would open both at once.
    expect(drawingKey(ENTITY.artifact_id, null)).not.toBe(drawingKey(ENTITY.artifact_id, 'occ-2'))
  })

  it('is stable for the same drawing', () => {
    expect(drawingKey(ENTITY.artifact_id, 'occ-2')).toBe(drawingKey(ENTITY.artifact_id, 'occ-2'))
  })
})

describe('the drawings an entity has', () => {
  it('is empty until one is added — the base drawing is not an occurrence', () => {
    expect(occurrencesOf({}, ENTITY.artifact_id)).toEqual([])
  })

  it('lists each added drawing', () => {
    const de = addOccurrence(addOccurrence({}, ENTITY), ENTITY)

    expect(occurrencesOf(de, ENTITY.artifact_id)).toHaveLength(2)
  })

  it('does not list another entity’s drawings', () => {
    const de = addOccurrence({}, ENTITY)

    expect(occurrencesOf(de, 'OTHER@1.bb.x')).toEqual([])
  })

  it('drops only the drawing removed', () => {
    const de = addOccurrence(addOccurrence({}, ENTITY), ENTITY)
    const first = occurrencesOf(de, ENTITY.artifact_id)[0]

    const after = removeOccurrence(de, first.id)

    expect(occurrencesOf(after, ENTITY.artifact_id).map((o) => o.id)).not.toContain(first.id)
    expect(occurrencesOf(after, ENTITY.artifact_id)).toHaveLength(1)
  })
})

describe('naming a drawing for the reader', () => {
  it('starts at the second, because the base drawing is the first', () => {
    expect(occurrenceOrdinal(0)).toBe('2nd')
    expect(occurrenceOrdinal(1)).toBe('3rd')
    expect(occurrenceOrdinal(2)).toBe('4th')
  })

  it('handles the teens, which do not follow the last digit', () => {
    expect(occurrenceOrdinal(9)).toBe('11th')
    expect(occurrenceOrdinal(10)).toBe('12th')
    expect(occurrenceOrdinal(11)).toBe('13th')
  })
})
