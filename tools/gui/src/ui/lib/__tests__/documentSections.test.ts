import { describe, it, expect } from 'vitest'
import {
  sectionAtOffset,
  findSectionSpec,
  sectionReferenceTerms,
  formatReferenceTerm,
  isLiteralEntityTypeTerm,
  parseReferenceTerm,
  rankedEntityTypeSet,
} from '../documentSections'

const BODY = `## Overview

Some overview text.

## Decision

The decision text, cursor lands here.

## Consequences

Consequence text.
`

describe('sectionAtOffset', () => {
  it('resolves the nearest preceding heading', () => {
    const offset = BODY.indexOf('The decision text')
    expect(sectionAtOffset(BODY, offset)).toBe('Decision')
  })

  it('returns null before any heading', () => {
    expect(sectionAtOffset(BODY, 0)).toBeNull()
  })

  it('resolves the last heading when the cursor is at the end', () => {
    expect(sectionAtOffset(BODY, BODY.length)).toBe('Consequences')
  })

  it('ignores level-3 headings', () => {
    const body = '## Overview\n\n### Sub-heading\n\ntext'
    const offset = body.indexOf('text')
    expect(sectionAtOffset(body, offset)).toBe('Overview')
  })
})

describe('findSectionSpec', () => {
  const sections = [
    { name: 'Overview' },
    { name: 'Decision', required_connections: ['requirement'] },
  ]

  it('finds a section by name', () => {
    expect(findSectionSpec(sections, 'Decision')?.name).toBe('Decision')
  })

  it('returns null for no match', () => {
    expect(findSectionSpec(sections, 'Consequences')).toBeNull()
  })

  it('returns null when name is null', () => {
    expect(findSectionSpec(sections, null)).toBeNull()
  })

  it('returns null when sections is undefined', () => {
    expect(findSectionSpec(undefined, 'Decision')).toBeNull()
  })
})

describe('sectionReferenceTerms', () => {
  it('concatenates required and suggested terms', () => {
    const section = {
      name: 'Decision',
      required_connections: ['requirement'],
      suggested_connections: ['@all'],
    }
    expect(sectionReferenceTerms(section)).toEqual(['requirement', '@all'])
  })

  it('returns an empty array for null section', () => {
    expect(sectionReferenceTerms(null)).toEqual([])
  })
})

describe('formatReferenceTerm', () => {
  it('labels @all as Any entity', () => {
    expect(formatReferenceTerm('@all')).toBe('Any entity')
  })

  it('strips a leading @ and title-cases the remainder', () => {
    expect(formatReferenceTerm('@BusinessActor')).toBe('BusinessActor')
  })

  it('title-cases bare snake_case terms', () => {
    expect(formatReferenceTerm('business_actor')).toBe('Business Actor')
  })
})

describe('isLiteralEntityTypeTerm / rankedEntityTypeSet', () => {
  it('treats bare terms as literal', () => {
    expect(isLiteralEntityTypeTerm('requirement')).toBe(true)
  })

  it('treats @-prefixed terms as non-literal', () => {
    expect(isLiteralEntityTypeTerm('@all')).toBe(false)
    expect(isLiteralEntityTypeTerm('@BusinessActor')).toBe(false)
  })

  it('ranked set keeps only literal terms', () => {
    const set = rankedEntityTypeSet(['requirement', '@all', 'goal'])
    expect(set).toEqual(new Set(['requirement', 'goal']))
  })

  it('ranked set is empty for undefined input', () => {
    expect(rankedEntityTypeSet(undefined)).toEqual(new Set())
  })
})

describe('parseReferenceTerm', () => {
  it('reads a bare term as an entity type', () => {
    expect(parseReferenceTerm('requirement')).toEqual({
      kind: 'entity', body: 'requirement',
    })
  })

  it('reads a class term as an entity term keeping its sigil', () => {
    expect(parseReferenceTerm('@internal-behavior-element').kind).toBe('entity')
    expect(parseReferenceTerm('@internal-behavior-element').body).toBe('@internal-behavior-element')
  })

  it('reads the doc: and diagram: prefixes', () => {
    expect(parseReferenceTerm('doc:adr')).toEqual({ kind: 'document', body: 'adr' })
    expect(parseReferenceTerm('diagram:c4-container')).toEqual({
      kind: 'diagram', body: 'c4-container',
    })
  })
})

describe('formatReferenceTerm across vocabularies', () => {
  it('names the kind for a document or diagram term', () => {
    expect(formatReferenceTerm('doc:adr')).toBe('Adr document')
    expect(formatReferenceTerm('diagram:c4-container')).toBe('C4 Container diagram')
  })

  it('prefers a declared document-type name over the humanised slug', () => {
    expect(formatReferenceTerm('doc:adr', [{ doc_type: 'adr', name: 'Architecture Decision Record' }]))
      .toBe('Architecture Decision Record document')
  })

  it('labels @all per vocabulary', () => {
    expect(formatReferenceTerm('doc:@all')).toBe('Any document')
    expect(formatReferenceTerm('diagram:@all')).toBe('Any diagram')
  })
})

describe('rankedEntityTypeSet excludes the other vocabularies', () => {
  // A `doc:` term names no entity type, and ranking an entity search by one would promote whatever
  // entity happened to share the name.
  it('drops document and diagram terms', () => {
    expect(rankedEntityTypeSet(['requirement', 'doc:adr', 'diagram:c4-container', '@all']))
      .toEqual(new Set(['requirement']))
  })
})
