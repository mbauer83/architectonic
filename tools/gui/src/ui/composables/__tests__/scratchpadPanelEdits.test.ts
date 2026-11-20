/**
 * What the note panel asks for, as edits of the document.
 *
 * The table used to be eleven inline handlers in the view's template, where nothing could assert
 * that an event reached the edit it names.
 */

import { describe, expect, it } from 'vitest'
import type { Scratchpad } from '../../../domain/schemas/scratchpads'
import { notePanelEdits } from '../scratchpadPanelEdits'

const pad: Scratchpad = {
  'artifact-id': 'SCR@1.a.pad',
  'artifact-type': 'scratchpad',
  name: 'Thinking',
  description: '',
  version: '0.1.1',
  status: 'draft',
  group: 'g',
  'meta-ontology': 'any',
  'classification-levels': [{
    id: 'kind', label: 'Kind', source: 'type', required: true, 'carries-attributes': true,
    options: [{ value: 'goal', within: '' }],
  }],
  notes: [
    { id: 'n1', title: 'A', area: 'unfiled', body: '', destination: 'undecided' },
    { id: 'n2', title: 'B', area: 'unfiled', body: '', destination: 'undecided' },
  ],
  links: [{ id: 'l1', source: 'n1', target: 'n2' }],
}

/** Run one panel event against the document and hand back what it became. */
function after(act: (edits: ReturnType<typeof notePanelEdits>) => void): Scratchpad {
  let current = pad
  act(notePanelEdits((next) => { current = next(current) }))
  return current
}

const note = (scratchpad: Scratchpad) => scratchpad.notes!.find((row) => row.id === 'n1')!

describe('a panel event becomes the edit it names', () => {
  it('narrows a note at a declared level, and re-opens it', () => {
    const refined = after((edits) => edits['refine-note']({ id: 'n1', levelId: 'kind', value: 'goal' }))

    expect(note(refined)['element-type']).toBe('goal')
    let reopened = refined
    notePanelEdits((next) => { reopened = next(reopened) })['unrefine-note']({ id: 'n1', levelId: 'kind' })
    expect(note(reopened)['element-type']).toBeUndefined()
  })

  it('sets a body, an attribute and a document type', () => {
    expect(note(after((edits) => edits['body-note']({ id: 'n1', body: 'Why' }))).body).toBe('Why')
    expect(note(after((edits) => edits['attribute-note']({ id: 'n1', name: 'Weight', value: 3 }))).attributes)
      .toEqual({ Weight: 3 })
    expect(note(after((edits) => edits['document-note']({ id: 'n1', documentType: 'adr' })))['document-type'])
      .toBe('adr')
  })

  it('types, reverses and untypes a link', () => {
    const typed = after((edits) => edits['type-link']({ id: 'l1', connectionType: 'serving' }))
    const reversed = after((edits) => edits['reverse-link']({ id: 'l1' }))

    expect(typed.links?.[0]['connection-type']).toBe('serving')
    expect([reversed.links?.[0].source, reversed.links?.[0].target]).toEqual(['n2', 'n1'])
  })

  it('applies every edit as one step through the function it was given', () => {
    let steps = 0
    const edits = notePanelEdits(() => { steps += 1 })

    edits['forget-note']({ id: 'n1' })
    edits['untype-note']({ id: 'n1' })
    edits['untype-link']({ id: 'l1' })

    expect(steps).toBe(3)
  })
})
