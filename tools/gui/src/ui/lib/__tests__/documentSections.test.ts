import { describe, it, expect } from 'vitest'
import {
  sectionAtOffset,
  findSectionSpec,
  sectionEntityTypeTerms,
  formatEntityTypeTerm,
  isLiteralEntityTypeTerm,
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
    { name: 'Decision', required_entity_type_connections: ['requirement'] },
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

describe('sectionEntityTypeTerms', () => {
  it('concatenates required and suggested terms', () => {
    const section = {
      name: 'Decision',
      required_entity_type_connections: ['requirement'],
      suggested_entity_type_connections: ['@all'],
    }
    expect(sectionEntityTypeTerms(section)).toEqual(['requirement', '@all'])
  })

  it('returns an empty array for null section', () => {
    expect(sectionEntityTypeTerms(null)).toEqual([])
  })
})

describe('formatEntityTypeTerm', () => {
  it('labels @all as Any entity', () => {
    expect(formatEntityTypeTerm('@all')).toBe('Any entity')
  })

  it('strips a leading @ and title-cases the remainder', () => {
    expect(formatEntityTypeTerm('@BusinessActor')).toBe('BusinessActor')
  })

  it('title-cases bare snake_case terms', () => {
    expect(formatEntityTypeTerm('business_actor')).toBe('Business Actor')
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
