import { describe, expect, it } from 'vitest'
import type { ChangeSummary } from '../../../domain/schemas/changes'
import {
  changeSubjectRoute,
  changedFieldsLabel,
  conditionExplanation,
  divergenceKey,
  isLongValue,
  stateExplanation,
} from '../ChangesView.helpers'

const change = (over: Partial<ChangeSummary> = {}): ChangeSummary => ({
  artifact_id: 'PCH@1.a.change-to-payments',
  target_id: 'REQ@1.b.payments',
  target_name: 'Payments',
  kind: 'entity',
  changed_fields: ['summary'],
  state: 'draft',
  condition: 'current',
  divergence: [],
  ...over,
})

describe('where a change is opened', () => {
  it('goes to the promoted artifact, in its own kind\'s view', () => {
    // These three asserted the reference, on the reasoning that it is what this repository holds.
    // It is also machinery — excluded from every list and every search — so linking it put a page in
    // front of readers showing a proxy and a description written for no one. The artifact a reader
    // knows is the promoted one: it is what search returns and what they edited.
    expect(changeSubjectRoute(change({ kind: 'entity' }))).toBe('/entities/REQ%401.b.payments')
  })

  it('opens a document change in the document view', () => {
    expect(changeSubjectRoute(change({ kind: 'document' }))).toBe('/documents/REQ%401.b.payments')
  })

  it('opens a diagram change in the diagram view', () => {
    expect(changeSubjectRoute(change({ kind: 'diagram' }))).toBe('/diagrams/REQ%401.b.payments')
  })

  it('always offers a link, because the promoted artifact is always addressable', () => {
    // There is no case with nothing to link to any more: the row names the promoted artifact, and
    // the local reference that used to be the link target is no longer published at all.
    expect(changeSubjectRoute(change())).toBe('/entities/REQ%401.b.payments')
  })
})

describe('what the row says', () => {
  it('names the fields the change touches', () => {
    expect(changedFieldsLabel(change({ changed_fields: ['name', 'summary'] }))).toBe('name, summary')
  })

  it('says nothing about a condition needing no action', () => {
    expect(conditionExplanation(change())).toBeNull()
  })

  it('explains staleness in words, not by colour alone', () => {
    expect(conditionExplanation(change({ condition: 'stale' }))).toMatch(/moved since/)
  })

  it('explains a conflict distinctly from staleness', () => {
    expect(conditionExplanation(change({ condition: 'conflicting' }))).toMatch(/disagree/)
  })

  it('warns that taking back a submitted change is visible to a reviewer', () => {
    expect(stateExplanation(change({ state: 'submitted' }))).toMatch(/withdraws it/)
  })

  it('says a draft has been put to nobody', () => {
    expect(stateExplanation(change())).toMatch(/Not sent/)
  })
})

describe('showing a value that would bury the row', () => {
  it('treats a short value as showable whole', () => {
    expect(isLongValue('A better title')).toBe(false)
  })

  it('treats a whole content section as needing to be clamped', () => {
    // `summary` covers the artifact's entire content section, so "what it says now" can be several
    // paragraphs — and a change replacing all of it with one line is what an author must see, at a
    // size they can still scan.
    expect(isLongValue('x'.repeat(241))).toBe(true)
  })

  it('has nothing to clamp when the value has no line to show', () => {
    expect(isLongValue(null)).toBe(false)
  })

  it('identifies one field of one change, so two rows do not expand together', () => {
    expect(divergenceKey('PCH@1', 'summary')).not.toBe(divergenceKey('PCH@2', 'summary'))
    expect(divergenceKey('PCH@1', 'summary')).not.toBe(divergenceKey('PCH@1', 'notes'))
  })
})
