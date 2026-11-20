/**
 * A note's attributes: which are offered, where editing starts, and what clearing one means.
 *
 * The level at which a schema applies is asserted against two ladders, because "once it has a
 * type" is one meta-ontology's answer and the declaration is what decides.
 */

import { describe, expect, it } from 'vitest'
import type { ClassificationLevel, Note, Scratchpad } from '../../../domain/schemas/scratchpads'
import {
  adHocTypeOf, adHocValue, attributeCell, attributeNameProblem, attributeRows, withAttribute,
} from '../scratchpadAttributes'
import { attributeLevel } from '../scratchpadClassification'

const level = (
  id: string, source: ClassificationLevel['source'], carries: boolean,
): ClassificationLevel => ({
  id, label: id, source, required: false, 'carries-attributes': carries, options: [],
})

const layered = [
  level('domain', 'hierarchy', false),
  level('entity_type', 'type', true),
  level('specialization', 'specializations', true),
]
/** Only the level below the type carries attributes. */
const catalogue = [level('kind', 'type', false), level('variant', 'specializations', true)]

const bare: Note = { id: 'n1', title: 'A', area: 'unfiled', body: '', destination: 'undecided' }
const typed: Note = { ...bare, destination: 'element', 'element-type': 'requirement' }

const pad = (note: Note): Scratchpad => ({
  'artifact-id': 'SCR@1.a.pad',
  'artifact-type': 'scratchpad',
  name: 'Thinking',
  description: '',
  version: '0.1.1',
  status: 'draft',
  group: 'g',
  'meta-ontology': 'any',
  notes: [note],
})

describe('the level a note takes its attribute schema from', () => {
  it('is none while the note is below every level that carries attributes', () => {
    expect(attributeLevel(bare, layered)).toBeNull()
    expect(attributeLevel({ ...bare, destination: 'element', domain: 'motivation' }, layered))
      .toBeNull()
  })

  it('is the deepest reached level that carries them', () => {
    expect(attributeLevel(typed, layered)?.id).toBe('entity_type')
    expect(attributeLevel({ ...typed, specialization: 'regulatory' }, layered)?.id)
      .toBe('specialization')
  })

  it('follows the declaration: a typed note is still below it where only a later level carries them', () => {
    expect(attributeLevel(typed, catalogue)).toBeNull()
    expect(attributeLevel({ ...typed, specialization: 'bolt' }, catalogue)?.id).toBe('variant')
  })
})

describe('the rows an editor shows', () => {
  it('offers what the schema declares, in its order, set or not', () => {
    expect(attributeRows({ Count: 3 }, ['Priority', 'Count'])).toEqual([
      { name: 'Priority', value: undefined, declared: true },
      { name: 'Count', value: 3, declared: true },
    ])
  })

  it('keeps an attribute the schema does not declare, marked as such', () => {
    expect(attributeRows({ Sponsor: 'CFO', Priority: 'high' }, ['Priority'])).toEqual([
      { name: 'Priority', value: 'high', declared: true },
      { name: 'Sponsor', value: 'CFO', declared: false },
    ])
  })

  it('renders a typed value as the cell a property input edits', () => {
    expect([undefined, 'far', 3, true, ['a', 'b']].map(attributeCell))
      .toEqual(['', 'far', '3', 'true', '["a","b"]'])
  })
})

describe('editing an attribute', () => {
  it('sets it without touching the others', () => {
    const before = pad({ ...typed, attributes: { Priority: 'high' } })

    const after = withAttribute(before, 'n1', 'Count', '3')

    expect(after.notes?.[0].attributes).toEqual({ Priority: 'high', Count: '3' })
    expect(before.notes?.[0].attributes).toEqual({ Priority: 'high' })
  })

  it('removes the key when the value is cleared, and the block with the last key', () => {
    const before = pad({ ...typed, attributes: { Priority: 'high', Count: '3' } })

    const one = withAttribute(before, 'n1', 'Count', '')
    const none = withAttribute(one, 'n1', 'Priority', '')

    expect(one.notes?.[0].attributes).toEqual({ Priority: 'high' })
    expect(none.notes?.[0]).not.toHaveProperty('attributes')
  })

  it('leaves the document alone for a note it does not hold', () => {
    const before = pad(typed)

    expect(withAttribute(before, 'ghost', 'Count', '3')).toEqual(before)
  })
})

describe('an attribute the schema does not declare', () => {
  it('is added to a note that has none', () => {
    const after = withAttribute(pad(typed), 'n1', 'Sponsor', 'CFO')

    expect(after.notes?.[0].attributes).toEqual({ Sponsor: 'CFO' })
  })

  it('stores a value of the type it was given', () => {
    expect(adHocValue('string', '3')).toBe('3')
    expect(adHocValue('integer', '3')).toBe(3)
    expect(adHocValue('number', '2.5')).toBe(2.5)
    expect(adHocValue('boolean', 'true')).toBe(true)
    expect(adHocValue('boolean', 'false')).toBe(false)
    expect(adHocValue('array', '["a","b"]')).toEqual(['a', 'b'])
  })

  it('keeps what was typed as text where it cannot be read as the chosen type', () => {
    expect(adHocValue('integer', 'three')).toBe('three')
    expect(adHocValue('integer', '2.5')).toBe('2.5')
    expect(adHocValue('integer', '')).toBe('')
    expect(adHocValue('array', '{"not":"a list"}')).toBe('{"not":"a list"}')
    expect(adHocValue('array', 'a, b')).toBe('a, b')
  })

  it('reads back the type a stored value was written as', () => {
    expect(['CFO', 3, 2.5, false, ['a']].map(adHocTypeOf))
      .toEqual(['string', 'integer', 'number', 'boolean', 'array'])
  })

  it('stores a typed value and removes it again', () => {
    const added = withAttribute(pad(typed), 'n1', 'Reviewed', false)

    expect(added.notes?.[0].attributes).toEqual({ Reviewed: false })
    expect(withAttribute(added, 'n1', 'Reviewed', '').notes?.[0]).not.toHaveProperty('attributes')
  })

  it('needs a name that is one line and not already listed', () => {
    const rows = attributeRows({ Sponsor: 'CFO' }, ['Priority'])

    expect(attributeNameProblem('  ', rows)).toMatch(/name/)
    expect(attributeNameProblem('two\nlines', rows)).toMatch(/one line/)
    expect(attributeNameProblem('Sponsor', rows)).toMatch(/already listed/)
    expect(attributeNameProblem(' Priority ', rows)).toMatch(/already listed/)
    expect(attributeNameProblem('Owner', rows)).toBeNull()
  })
})
