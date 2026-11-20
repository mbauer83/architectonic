/**
 * A note is refined through the levels its scratchpad was served, whatever they are.
 *
 * Two ladders, on purpose. The first has the shape the shipped ontology declares. The second
 * shares neither its names nor its count — no level above the type, and a required one below it —
 * because code that hard-coded "domain, then type" would pass every case written against the first.
 */

import { describe, expect, it } from 'vitest'
import type {
  Area, ClassificationLevel, Note, Scratchpad,
} from '../../../domain/schemas/scratchpads'
import {
  optionsAt, valueAt, withLevelValue, withoutLevelValue,
} from '../scratchpadClassification'

const layered: ClassificationLevel[] = [
  {
    id: 'domain', label: 'Domain', source: 'hierarchy', required: true, 'carries-attributes': false,
    options: [{ value: 'motivation', within: '' }, { value: 'application', within: '' }],
  },
  {
    id: 'entity_type', label: 'Entity type', source: 'type', required: true,
    'carries-attributes': true,
    options: [
      { value: 'goal', within: 'motivation' },
      { value: 'requirement', within: 'motivation' },
      { value: 'application-component', within: 'application' },
    ],
  },
  {
    id: 'specialization', label: 'Specialization', source: 'specializations', required: false,
    'carries-attributes': true,
    options: [
      { value: 'regulatory', within: 'requirement' },
      { value: 'microservice', within: 'application-component' },
    ],
  },
]

const catalogue: ClassificationLevel[] = [
  {
    id: 'kind', label: 'Kind of part', source: 'type', required: true, 'carries-attributes': false,
    options: [{ value: 'fastener', within: '' }, { value: 'bearing', within: '' }],
  },
  {
    id: 'variant', label: 'Variant', source: 'specializations', required: true,
    'carries-attributes': true,
    options: [{ value: 'bolt', within: 'fastener' }, { value: 'ball', within: 'bearing' }],
  },
]

const bare: Note = { id: 'n1', title: 'A', area: 'strategy', body: '', destination: 'undecided' }

const pad = (levels: ClassificationLevel[], note: Note = bare): Scratchpad => ({
  'artifact-id': 'SCR@1.a.pad',
  'artifact-type': 'scratchpad',
  name: 'Thinking',
  description: '',
  version: '0.1.1',
  status: 'draft',
  group: 'g',
  'meta-ontology': 'any',
  'classification-levels': levels,
  notes: [note],
})

const noteOf = (scratchpad: Scratchpad): Note => scratchpad.notes![0]

const strategy: Area = {
  id: 'strategy', label: 'Vision & strategy',
  'permitted-domains': ['motivation'], 'permitted-element-types': ['goal', 'requirement'],
}

describe('narrowing a note one declared level at a time', () => {
  it('sets the value under the key its level takes values from', () => {
    const narrowed = noteOf(withLevelValue(pad(layered), 'n1', 'domain', 'motivation'))

    expect(narrowed.destination).toBe('element')
    expect(valueAt(narrowed, layered[0])).toBe('motivation')
    expect(valueAt(narrowed, layered[1])).toBeUndefined()
  })

  it('re-opens every level declared after the one re-answered', () => {
    const specialized = withLevelValue(
      withLevelValue(pad(layered), 'n1', 'entity_type', 'requirement'),
      'n1', 'specialization', 'regulatory',
    )

    const again = noteOf(withLevelValue(specialized, 'n1', 'entity_type', 'goal'))

    expect(valueAt(again, layered[1])).toBe('goal')
    expect(valueAt(again, layered[2])).toBeUndefined()
  })

  it('answers the levels above a value that implies them', () => {
    const chosen = noteOf(withLevelValue(pad(layered), 'n1', 'specialization', 'microservice'))

    expect(layered.map((level) => valueAt(chosen, level))).toEqual(
      ['application', 'application-component', 'microservice'],
    )
  })

  it('drops a document type, since a note has one destination', () => {
    const document: Note = { ...bare, destination: 'document', 'document-type': 'adr' }

    const narrowed = noteOf(withLevelValue(pad(layered, document), 'n1', 'domain', 'motivation'))

    expect(narrowed['document-type']).toBeUndefined()
  })

  it('leaves a note tied to the model alone', () => {
    const bound: Note = {
      ...bare, destination: 'element', 'element-type': 'goal',
      'model-ref': { 'artifact-id': 'GOL@1.a.x', kind: 'bound' },
    }
    const before = pad(layered, bound)

    expect(withLevelValue(before, 'n1', 'entity_type', 'requirement')).toEqual(before)
    expect(withoutLevelValue(before, 'n1', 'entity_type')).toEqual(before)
  })

  it('ignores a level the scratchpad was not served', () => {
    const before = pad(catalogue)

    expect(withLevelValue(before, 'n1', 'domain', 'motivation')).toEqual(before)
  })
})

describe('re-opening a level', () => {
  it('keeps what was decided above it', () => {
    const typed = withLevelValue(pad(layered), 'n1', 'entity_type', 'goal')

    const reopened = noteOf(withoutLevelValue(typed, 'n1', 'entity_type'))

    expect(valueAt(reopened, layered[0])).toBe('motivation')
    expect(valueAt(reopened, layered[1])).toBeUndefined()
    expect(reopened.destination).toBe('element')
  })

  it('returns the note to undecided once nothing is left', () => {
    const narrowed = withLevelValue(pad(layered), 'n1', 'domain', 'motivation')

    expect(noteOf(withoutLevelValue(narrowed, 'n1', 'domain')).destination).toBe('undecided')
  })
})

describe('what a level offers', () => {
  it('offers what the level above allows', () => {
    const inMotivation = noteOf(withLevelValue(pad(layered), 'n1', 'domain', 'motivation'))

    expect(optionsAt(inMotivation, layered[1], layered, null).map((option) => option.value))
      .toEqual(['goal', 'requirement'])
  })

  it('offers everything while the level above is undecided', () => {
    expect(optionsAt(bare, layered[1], layered, null)).toHaveLength(3)
  })

  it('offers what the area permits first, and marks the rest rather than hiding it', () => {
    const offered = optionsAt(bare, layered[1], layered, strategy)

    expect(offered).toEqual([
      { value: 'goal', outsideArea: false },
      { value: 'requirement', outsideArea: false },
      { value: 'application-component', outsideArea: true },
    ])
    expect(optionsAt(bare, layered[0], layered, strategy)).toEqual([
      { value: 'motivation', outsideArea: false },
      { value: 'application', outsideArea: true },
    ])
  })

  it('marks nothing where the area says nothing about the level, or there is no area', () => {
    expect(optionsAt(bare, layered[2], layered, strategy).some((option) => option.outsideArea))
      .toBe(false)
    expect(optionsAt(bare, layered[1], layered, null).some((option) => option.outsideArea))
      .toBe(false)
    expect(
      optionsAt(bare, layered[1], layered, { id: 'p', label: 'Portfolio' })
        .some((option) => option.outsideArea),
    ).toBe(false)
  })
})

describe('a ladder of another shape', () => {
  it('has no level above the type, and takes the first choice at the type', () => {
    const chosen = noteOf(withLevelValue(pad(catalogue), 'n1', 'kind', 'fastener'))

    expect(catalogue.map((level) => valueAt(chosen, level))).toEqual(['fastener', undefined])
    expect(chosen.domain).toBeUndefined()
  })

  it('offers at its second level what its first allows', () => {
    const fastener = noteOf(withLevelValue(pad(catalogue), 'n1', 'kind', 'fastener'))

    expect(optionsAt(fastener, catalogue[1], catalogue, null).map((option) => option.value))
      .toEqual(['bolt'])
  })

  it('re-opens the variant when the kind is re-answered', () => {
    const bolt = withLevelValue(
      withLevelValue(pad(catalogue), 'n1', 'kind', 'fastener'), 'n1', 'variant', 'bolt',
    )

    const again = noteOf(withLevelValue(bolt, 'n1', 'kind', 'bearing'))

    expect(catalogue.map((level) => valueAt(again, level))).toEqual(['bearing', undefined])
  })
})
