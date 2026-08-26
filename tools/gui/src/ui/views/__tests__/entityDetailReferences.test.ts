/**
 * How each kind of reference reads as a row.
 *
 * Three near-identical components became one list plus these three mappings, and this is where the
 * behaviour went: the list draws rows and never learns which kind it has, so everything a reader
 * actually sees about a document's section, a diagram's type or a pad's status is decided here.
 */

import { describe, expect, it } from 'vitest'
import {
  diagramReferenceRows,
  documentReferenceRows,
  scratchpadReferenceRows,
} from '../EntityDetailView.references'
import type { EntityDetail } from '../../../domain'

type DocRef = NonNullable<EntityDetail['referenced_in_documents']>[number]

/** A document reference, stating only the part each test is about. */
const docRef = (over: Partial<DocRef> = {}): DocRef => ({
  document_id: 'ADR@1.a.one', title: 'One', doc_type: 'adr', section: 'Context', href: '#a',
  label: 'One', path: 'docs/adr/one.md', ...over,
})

describe('a document reference', () => {
  const rows = documentReferenceRows([
    docRef({ section: 'Context', href: '#a' }),
  ])

  it('links to the document and is named by its title', () => {
    expect(rows[0].to).toBe('/documents/ADR%401.a.one')
    expect(rows[0].name).toBe('One')
  })

  it('says which section the link sits in, because that is what a document reference carries', () => {
    expect(rows[0].meta).toBe('adr · Context')
  })

  it('says only the type where there is no section', () => {
    const [row] = documentReferenceRows([
      docRef({ section: '' }),
    ])

    expect(row.meta).toBe('adr')
  })

  it('is keyed by document, section and href together', () => {
    // One document can reference an entity from several sections, and a section from several links.
    const two = documentReferenceRows([
      docRef({ section: 'Context', href: '#a' }),
      docRef({ section: 'Context', href: '#b' }),
    ])

    expect(new Set(two.map(r => r.key)).size).toBe(2)
  })
})

describe('a diagram reference', () => {
  it('strips the ontology prefix a reader of the diagram already knows', () => {
    const [row] = diagramReferenceRows([
      { artifact_id: 'ARC@1.a.view', name: 'A View', diagram_type: 'archimate-motivation', status: 'active' },
    ])

    expect(row.meta).toBe('motivation')
  })

  it('says the status when it is not active, because a draft drawing is a weaker statement', () => {
    const [row] = diagramReferenceRows([
      { artifact_id: 'ARC@1.a.view', name: 'A View', diagram_type: 'archimate-motivation', status: 'draft' },
    ])

    expect(row.meta).toBe('motivation · draft')
  })

  it('links to the diagram', () => {
    const [row] = diagramReferenceRows([
      { artifact_id: 'ARC@1.a.view', name: 'A View', diagram_type: 'c4-container', status: 'active' },
    ])

    expect(row.to).toBe('/diagrams/ARC%401.a.view')
  })
})

describe('a scratchpad reference', () => {
  it('carries no type, because a pad has none to carry', () => {
    const [row] = scratchpadReferenceRows([
      { artifact_id: 'SCR@1.a.pad', name: 'A Pad', status: 'active' },
    ])

    expect(row.meta).toBe('')
    expect(row.to).toBe('/scratchpads/SCR%401.a.pad')
  })

  it('says the status when it is not active', () => {
    const [row] = scratchpadReferenceRows([
      { artifact_id: 'SCR@1.a.pad', name: 'A Pad', status: 'draft' },
    ])

    expect(row.meta).toBe('draft')
  })
})

describe('every kind', () => {
  it('produces one row per reference and none for an empty list', () => {
    expect(documentReferenceRows([])).toEqual([])
    expect(diagramReferenceRows([])).toEqual([])
    expect(scratchpadReferenceRows([])).toEqual([])
  })
})
