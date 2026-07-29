import { describe, it, expect } from 'vitest'
import { viewpointOptionLabel, findViewpointBySlug } from '../ViewpointSelect.helpers'
import type { ViewpointSummary } from '../../../domain'

const motivation: ViewpointSummary = {
  slug: 'motivation', version: 1, name: 'Motivation', description: '', purpose: [], content: [], scope: {},
}
const layered: ViewpointSummary = {
  slug: 'layered', version: 2, name: 'Layered', description: '', purpose: [], content: [], scope: {},
}

describe('viewpointOptionLabel', () => {
  it('combines name and version', () => {
    expect(viewpointOptionLabel(motivation)).toBe('Motivation (v1)')
  })
})

describe('findViewpointBySlug', () => {
  const viewpoints = [motivation, layered]

  it('returns null for a null slug (unrestricted)', () => {
    expect(findViewpointBySlug(viewpoints, null)).toBeNull()
  })

  it('finds a matching viewpoint by slug', () => {
    expect(findViewpointBySlug(viewpoints, 'layered')).toEqual(layered)
  })

  it('returns null for an unknown slug', () => {
    expect(findViewpointBySlug(viewpoints, 'does-not-exist')).toBeNull()
  })
})
