/**
 * The document the canvas edits, and its undo history.
 *
 * Undo is asserted here rather than left to the browser suite because the property that matters is
 * not "the button works" — it is that the history is a sequence of whole documents, so no edit kind
 * can be subtly non-reversible. An inverse-per-operation stack is where that bug lives.
 */

import { describe, expect, it } from 'vitest'
import type { Note, Scratchpad } from '../../../domain/schemas/scratchpads'
import { useScratchpadDocument } from '../useScratchpadDocument'
import {
  toReplacePayload,
  withBinding,
  withLink,
  withLinkType,
  withNote,
  withNoteAt,
  areaAtPoint,
  withReversedLink,
  withType,
  withoutBinding,
  withoutLink,
  withoutLinkType,
  withoutNote,
  withoutRealization,
  withoutType,
} from '../scratchpadEdits'

/** A note as the server sends one: `body` and `destination` carry their resolved defaults. */
const note = (id: string, title: string, area = 'unfiled'): Note =>
  ({ id, title, area, body: '', destination: 'undecided' })

const base: Scratchpad = {
  'artifact-id': 'SCR@1.a.pad',
  'artifact-type': 'scratchpad',
  name: 'Thinking',
  description: '',
  version: '0.1.1',
  status: 'draft',
  group: 'strategy-and-value',
  'meta-ontology': 'archimate-4',
  areas: [{ id: 'strategy', label: 'Vision & strategy' }],
  notes: [note('n1', 'Grow into mid-market', 'strategy')],
  links: [],
  layout: { areas: { strategy: [0, 0, 1200, 600] }, notes: { n1: [40, 60] } },
}

describe('the edited document', () => {
  it('starts empty and adopts a loaded scratchpad without making it undoable', () => {
    const document = useScratchpadDocument()

    document.adopt(base)

    expect(document.current.value).toEqual(base)
    expect(document.canUndo.value).toBe(false)
    expect(document.dirty.value).toBe(false)
  })

  it('marks the document dirty on an edit and clean when the server answers', () => {
    const document = useScratchpadDocument()
    document.adopt(base)

    document.commit(withNoteAt(base, 'n1', 200, 300))
    expect(document.dirty.value).toBe(true)

    document.adopt({ ...base, version: '0.1.2' })
    expect(document.dirty.value).toBe(false)
  })

  it('undoes and redoes an edit', () => {
    const document = useScratchpadDocument()
    document.adopt(base)
    document.commit(withNoteAt(base, 'n1', 200, 300))

    document.undo()
    expect(document.current.value?.layout?.notes?.n1).toEqual([40, 60])

    document.redo()
    expect(document.current.value?.layout?.notes?.n1).toEqual([200, 300])
  })

  it('undoes edits of every kind, because the history holds documents rather than inverses', () => {
    const document = useScratchpadDocument()
    document.adopt(base)

    document.commit(withNote(document.current.value!, note('n2', 'Second')))
    document.commit(withLink(document.current.value!, 'l1', 'n1', 'n2'))
    document.commit(withoutNote(document.current.value!, 'n1'))

    document.undo()
    expect(document.current.value?.notes?.map((note) => note.id).sort()).toEqual(['n1', 'n2'])
    document.undo()
    expect(document.current.value?.links).toEqual([])
    document.undo()
    expect(document.current.value?.notes?.map((note) => note.id)).toEqual(['n1'])
    expect(document.canUndo.value).toBe(false)
  })

  it('discards the redo branch once a new edit lands on it', () => {
    const document = useScratchpadDocument()
    document.adopt(base)
    document.commit(withNoteAt(base, 'n1', 200, 300))
    document.undo()

    document.commit(withNoteAt(base, 'n1', 500, 500))

    // Redoing to a document that was never in this history is the one thing undo must not do.
    expect(document.canRedo.value).toBe(false)
  })

  it('does nothing when there is nothing to undo', () => {
    const document = useScratchpadDocument()
    document.adopt(base)

    document.undo()
    document.redo()

    expect(document.current.value).toEqual(base)
  })
})

describe('the edits themselves', () => {
  it('snaps a placement to the grid, so a save does not visibly nudge the note', () => {
    expect(withNoteAt(base, 'n1', 41.4, 58.9).layout?.notes?.n1).toEqual([40, 60])
  })

  it('deletes a note together with its links', () => {
    const withTwo = withLink(withNote(base, note('n2', 'Second')), 'l1', 'n1', 'n2')

    const after = withoutNote(withTwo, 'n1')

    expect(after.links).toEqual([])
    expect(after.layout?.notes?.n1).toBeUndefined()
  })

  it('rubs out a link, leaving both notes where they are', () => {
    // Deciding two things are not related after all is thinking. Before this the only way to
    // remove a link was to delete a note it touched, which removed the thought as well.
    const withTwo = withLink(withNote(base, note('n2', 'Second')), 'l1', 'n1', 'n2')

    const after = withoutLink(withTwo, 'l1')

    expect(after.links).toEqual([])
    expect(after.notes).toHaveLength(2)
  })

  it('takes a relation off a link without removing the link', () => {
    const withTwo = withNote(base, note('n2', 'Second'))
    const typed = withLinkType(withLink(withTwo, 'l1', 'n1', 'n2'), 'l1', 'archimate-realization')

    const after = withoutLinkType(typed, 'l1')

    // Removed, never emptied: the wire shape is optional-key, so `''` would have been written to
    // the file as a relation with no name rather than as no relation.
    expect(after.links?.[0]).not.toHaveProperty('connection-type')
    expect(after.links).toHaveLength(1)
  })

  it('refuses a duplicate link and a self-link, in either direction', () => {
    const withTwo = withNote(base, note('n2', 'Second'))
    const once = withLink(withTwo, 'l1', 'n1', 'n2')

    expect(withLink(once, 'l2', 'n1', 'n2').links).toHaveLength(1)
    expect(withLink(once, 'l3', 'n2', 'n1').links).toHaveLength(1)
    expect(withLink(once, 'l4', 'n1', 'n1').links).toHaveLength(1)
  })
})

describe('the replace payload', () => {
  it('omits the two fields the server derives, since the client does not own them', () => {
    const payload = toReplacePayload(base)

    expect(payload).not.toHaveProperty('group')
    expect((payload.notes as Array<Record<string, unknown>>)[0]).not.toHaveProperty('area')
  })

  it('keeps everything the server does not derive', () => {
    const payload = toReplacePayload(base)

    expect(payload['artifact-id']).toBe('SCR@1.a.pad')
    expect(payload.layout).toEqual(base.layout)
    expect((payload.notes as Array<Record<string, unknown>>)[0].title).toBe('Grow into mid-market')
  })
})


describe('binding a note to something that already exists', () => {
  const capability = { artifact_id: 'CAP@1.a.onboarding', artifact_type: 'capability' }

  it('takes the type from the entity, because the entity is the authority on what it is', () => {
    const bound = withBinding(base, 'n1', capability)

    const note = bound.notes?.[0]
    expect(note?.destination).toBe('element')
    expect(note?.['element-type']).toBe('capability')
    expect(note?.['model-ref']).toEqual({ 'artifact-id': 'CAP@1.a.onboarding', kind: 'bound' })
  })

  it('binds one entity once, so the canvas never shows a duplicate it cannot resolve', () => {
    const two = withNote(base, note('n2', 'Second'))
    const once = withBinding(two, 'n1', capability)

    const twice = withBinding(once, 'n2', capability)

    expect(twice.notes?.filter((candidate) => candidate['model-ref'])).toHaveLength(1)
  })

  it('releases a binding without touching the title, which was the note\'s own', () => {
    const bound = withBinding(base, 'n1', capability)

    const released = withoutBinding(bound, 'n1')

    expect(released.notes?.[0]['model-ref']).toBeUndefined()
    expect(released.notes?.[0]['element-type']).toBeUndefined()
    expect(released.notes?.[0].destination).toBe('undecided')
    expect(released.notes?.[0].title).toBe('Grow into mid-market')
  })

  it('leaves a realized note alone — dropping that reference is forgetting, a different act', () => {
    const realized = withNote(base, {
      ...note('n1', 'Grow into mid-market', 'strategy'),
      destination: 'element',
      'element-type': 'capability',
      'model-ref': { 'artifact-id': 'CAP@1.a.x', kind: 'realized' },
    })

    expect(withoutBinding(realized, 'n1')).toEqual(realized)
  })

  it('binding is undoable like any other edit', () => {
    const doc = useScratchpadDocument()
    doc.adopt(base)

    doc.commit(withBinding(base, 'n1', capability))
    doc.undo()

    expect(doc.current.value?.notes?.[0]['model-ref']).toBeUndefined()
  })
})


describe('refining a note down the ontology', () => {
  it('narrows a note to an element type', () => {
    const typed = withType(base, 'n1', 'requirement')

    expect(typed.notes?.[0].destination).toBe('element')
    expect(typed.notes?.[0]['element-type']).toBe('requirement')
  })

  it('untyping clears every link touching the note', () => {
    // A typed link with an untyped end is a claim nothing supports, and the server rejects the
    // document that asserts it.
    const two = withNote(base, note('n2', 'Second'))
    const linked = withLinkType(withLink(two, 'l1', 'n1', 'n2'), 'l1', 'archimate-realization')

    const after = withoutType(withType(linked, 'n1', 'requirement'), 'n1')

    expect(after.links?.[0]['connection-type']).toBeUndefined()
  })

  it('refuses to retype a note that takes its type from the model', () => {
    const bound = withBinding(base, 'n1', { artifact_id: 'CAP@1.a.x', artifact_type: 'capability' })

    expect(withType(bound, 'n1', 'goal')).toEqual(bound)
    expect(withoutType(bound, 'n1')).toEqual(bound)
  })

  it('forgets a realization without touching the type it describes', () => {
    const realized = withNote(base, {
      ...note('n1', 'Grow into mid-market', 'strategy'),
      destination: 'element',
      'element-type': 'capability',
      'model-ref': { 'artifact-id': 'CAP@1.a.x', kind: 'realized' },
    })

    const after = withoutRealization(realized, 'n1')

    expect(after.notes?.[0]['model-ref']).toBeUndefined()
    expect(after.notes?.[0]['element-type']).toBe('capability')
  })

  it('reverses a link, which is the remedy that leads on a refused triple', () => {
    const two = withLink(withNote(base, note('n2', 'Second')), 'l1', 'n1', 'n2')

    const reversed = withReversedLink(two, 'l1')

    expect(reversed.links?.[0].source).toBe('n2')
    expect(reversed.links?.[0].target).toBe('n1')
  })

  it('types a link from the alternatives the verdict offered', () => {
    const two = withLink(withNote(base, note('n2', 'Second')), 'l1', 'n1', 'n2')

    expect(withLinkType(two, 'l1', 'archimate-serving').links?.[0]['connection-type'])
      .toBe('archimate-serving')
  })

  it('files a point in the smallest containing frame, and outside every frame in none', () => {
    // Mirrors `Scratchpad.area_of`: smallest wins, so dropping into a small frame lying on a large
    // one means the small one — and declaration order is never the tie-break, because the file is
    // written in stable id order and a note would otherwise move frames by being saved.
    const nested: Scratchpad = {
      ...base,
      areas: [...(base.areas ?? []), { id: 'inner', label: 'Inner' }],
      layout: { ...base.layout, areas: { strategy: [0, 0, 1200, 600], inner: [100, 100, 300, 200] } },
    }

    expect(areaAtPoint(nested, 200, 150)).toBe('inner')
    expect(areaAtPoint(nested, 900, 500)).toBe('strategy')
    expect(areaAtPoint(nested, 5000, 5000)).toBe('unfiled')
  })
})

describe('where a link meets a note', () => {
  const BOX = { width: 132, height: 120 }

  it('leaves by the side the other note lies on, not from the centre', async () => {
    const { anchor } = await import('../scratchpadLinkGeometry')

    // Directly to the right: out of the right-hand side, at its middle.
    expect(anchor({ x: 0, y: 0 }, { x: 400, y: 0 }, BOX)).toEqual({ x: 132, y: 60 })
    // Directly below: out of the bottom, at its middle.
    expect(anchor({ x: 0, y: 0 }, { x: 0, y: 400 }, BOX)).toEqual({ x: 66, y: 120 })
    // Above and slightly right: the dominant axis decides, so it is still the top.
    expect(anchor({ x: 0, y: 400 }, { x: 40, y: 0 }, BOX)).toEqual({ x: 66, y: 400 })
  })

  it('draws a curve that starts and ends on those sides', async () => {
    const { linkPath } = await import('../scratchpadLinkGeometry')

    // Centre-to-centre put the arrowhead under the note it pointed at, which is where the
    // ontology's notation is least useful.
    expect(linkPath({ x: 0, y: 0 }, { x: 400, y: 0 }, BOX)).toMatch(/^M132,60 C/)
    expect(linkPath({ x: 0, y: 0 }, { x: 400, y: 0 }, BOX)).toMatch(/400,60$/)
  })
})
