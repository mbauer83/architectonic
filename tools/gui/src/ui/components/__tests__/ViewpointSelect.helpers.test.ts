import { describe, it, expect } from 'vitest'
import {
  viewpointOptionLabel, findViewpointBySlug, suitsDiagramType, viewpointOptions,
} from '../ViewpointSelect.helpers'
import type { ViewpointSummary } from '../../../domain'

const motivation: ViewpointSummary = {
  slug: 'motivation', version: 1, name: 'Motivation', description: '', purpose: [], content: [], scope: {},
  intended_for: ['archimate-motivation'],
}
const layered: ViewpointSummary = {
  slug: 'layered', version: 2, name: 'Layered', description: '', purpose: [], content: [], scope: {},
  intended_for: ['archimate-layered'],
}
const anything: ViewpointSummary = {
  slug: 'anything', version: 1, name: 'Anything', description: '', purpose: [], content: [], scope: {},
  intended_for: [],
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

describe('viewpointOptions', () => {
  it('lists the viewpoints intended for the diagram type first, and marks the rest', () => {
    const options = viewpointOptions([layered, motivation, anything], 'archimate-motivation')

    expect(options.map((o) => [o.viewpoint.slug, o.suited])).toEqual([
      ['motivation', true], ['anything', true], ['layered', false],
    ])
  })

  it('treats a viewpoint declaring no types as suited to any', () => {
    expect(suitsDiagramType(anything, 'c4-container')).toBe(true)
  })

  it('marks nothing where no diagram type is in question', () => {
    expect(viewpointOptions([layered, motivation], undefined).every((o) => o.suited)).toBe(true)
  })
})
