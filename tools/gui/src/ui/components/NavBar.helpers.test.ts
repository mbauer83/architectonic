import { describe, it, expect } from 'vitest'
import { browseTarget } from './NavBar.helpers'

describe('where Browse goes', () => {
  it('keeps the filters you already have while browsing', () => {
    expect(browseTarget('/entities', { domain: 'motivation', type: 'goal' }))
      .toEqual({ path: '/entities', query: { domain: 'motivation', type: 'goal' } })
  })

  it('carries nothing from a diagram page', () => {
    // `type` is the *diagram* type there. Carried across it became an entity-type filter no entity
    // matches, so the select went blank and the list emptied until something reset it.
    expect(browseTarget('/diagrams/create', { type: 'archimate-business' })).toBe('/entities')
  })

  it('carries nothing from an entity’s own pages, which hold no list filters', () => {
    expect(browseTarget('/entities/GOL%401.aa.x', { type: 'goal' })).toBe('/entities')
  })

  it('keeps the enterprise browser’s filters too', () => {
    expect(browseTarget('/global/entities', { view: 'groups' }))
      .toEqual({ path: '/entities', query: { view: 'groups' } })
  })

  it('is the plain route when there is nothing to carry', () => {
    expect(browseTarget('/entities', {})).toBe('/entities')
    expect(browseTarget('/entities', { type: '' })).toBe('/entities')
  })

  it('ignores a repeated parameter rather than passing an array along', () => {
    expect(browseTarget('/entities', { type: ['goal', 'driver'] })).toBe('/entities')
  })
})
