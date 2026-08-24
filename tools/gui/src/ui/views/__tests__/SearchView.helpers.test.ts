import { describe, expect, it } from 'vitest'

import { hitKindLabel, hitTypeLabel } from '../SearchView.helpers'

/**
 * The type a search result shows.
 *
 * A diagram's `artifact_type` is the constant `"diagram"` — its kind, not its type — so the list gave
 * one undifferentiated chip to a C4 deployment view, an activity walkthrough and an ArchiMate
 * motivation view, while documents showed `adr` and entities showed `application-component`. The
 * specific type was already on the wire under `diagram_type`; the view did not read it.
 */

describe('the type a hit shows', () => {
  it('reads a diagram type for a diagram', () => {
    expect(hitTypeLabel({
      record_type: 'diagram', artifact_type: 'diagram', diagram_type: 'c4-deployment',
    })).toBe('c4-deployment')
  })

  it('never shows a diagram the kind it already shows beside it', () => {
    expect(hitTypeLabel({
      record_type: 'diagram', artifact_type: 'diagram', diagram_type: 'activity',
    })).not.toBe('diagram')
  })

  it('reads the artifact type for an entity', () => {
    expect(hitTypeLabel({ record_type: 'entity', artifact_type: 'application-component' }))
      .toBe('application-component')
  })

  it('reads the doc type for a document, which arrives as artifact_type', () => {
    expect(hitTypeLabel({ record_type: 'document', artifact_type: 'adr' })).toBe('adr')
  })

  it('gives a diagram with no declared type nothing rather than its kind', () => {
    expect(hitTypeLabel({ record_type: 'diagram', artifact_type: 'diagram', diagram_type: null }))
      .toBeNull()
  })

  it('gives an untyped note nothing, leaving the wording to the view', () => {
    expect(hitTypeLabel({ record_type: 'scratchpad-note', artifact_type: '' })).toBeNull()
  })
})

describe('the kind a hit shows', () => {
  it.each([
    ['entity', 'entity'],
    ['diagram', 'diagram'],
    ['document', 'document'],
    ['connection', 'relationship'],
    ['scratchpad-note', 'note'],
    ['assurance-node', 'assurance'],
  ])('names %s', (recordType, expected) => {
    expect(hitKindLabel(recordType)).toBe(expected)
  })

  it('passes an unknown kind through rather than calling it an artifact', () => {
    expect(hitKindLabel('viewpoint')).toBe('viewpoint')
  })
})
