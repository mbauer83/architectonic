import { describe, expect, it } from 'vitest'
import type { ChangeSummary } from '../../../domain/schemas/changes'
import {
  canBeRebased,
  changeSubjectRoute,
  changedFieldsLabel,
  conditionExplanation,
  divergenceKey,
  isLongValue,
  rebaseOutcomeMessage,
  stateExplanation,
  submitLabel,
  submittableIds,
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

describe('when a rebase is worth offering', () => {
  it('is not offered on a change that already sits on the current version', () => {
    // Offering it would invite a reader to fix what is not broken.
    expect(canBeRebased(change({ condition: 'current' }))).toBe(false)
  })

  it('is offered on a stale change, which is what it is for', () => {
    expect(canBeRebased(change({ condition: 'stale' }))).toBe(true)
  })

  it('is offered on a conflicting one, because rehearsing is how you find out why', () => {
    expect(canBeRebased(change({ condition: 'conflicting' }))).toBe(true)
  })
})

describe('what a rebase concluded', () => {
  it('says it landed, for a clean outcome', () => {
    expect(rebaseOutcomeMessage('clean', 'replays onto X')).toMatch(/Brought onto/)
  })

  it('points at the discard for a superseded one, rather than calling it a conflict', () => {
    expect(rebaseOutcomeMessage('superseded', 'X already says it')).toMatch(/discard/)
  })

  it("carries the verifier's own words for a conflict, and says nothing was written", () => {
    const message = rebaseOutcomeMessage('conflicting', 'E031: the display section is missing')
    expect(message).toContain('E031: the display section is missing')
    expect(message).toMatch(/nothing was written/)
  })
})


describe('what a submission would carry', () => {
  it('takes the drafts, in the order the page shows them', () => {
    const ids = submittableIds([
      change({ artifact_id: 'PCH@2.b.second' }),
      change({ artifact_id: 'PCH@1.a.first' }),
    ])

    expect(ids).toEqual(['PCH@2.b.second', 'PCH@1.a.first'])
  })

  it('leaves out one already submitted, which is rebased rather than submitted again', () => {
    const ids = submittableIds([
      change({ artifact_id: 'PCH@1.a.draft' }),
      change({ artifact_id: 'PCH@2.b.sent', state: 'submitted' }),
    ])

    expect(ids).toEqual(['PCH@1.a.draft'])
  })

  it('offers nothing when everything is already under review', () => {
    expect(submittableIds([change({ state: 'submitted' })])).toEqual([])
  })

  it('counts what it would carry, in the singular where there is one', () => {
    expect(submitLabel(1)).toBe('Submit 1 change for review')
    expect(submitLabel(3)).toBe('Submit 3 changes for review')
  })
})
