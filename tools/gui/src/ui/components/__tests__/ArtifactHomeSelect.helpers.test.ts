import { describe, expect, it } from 'vitest'
import type { GroupEntry, GroupList } from '../../../domain/schemas/groups'
import {
  NO_COLLECTION,
  defaultHome,
  homeForCreate,
  homeForMove,
  homeOptions,
} from '../ArtifactHomeSelect.helpers'

const entry = (over: Partial<GroupEntry> = {}): GroupEntry => ({
  slug: 'platform-core', id: 'GRP@1', name: 'Platform Core', description: '',
  order: 1, archived: false, default: false, meta_ontology: '', type_filter: [],
  member_count: 3, ...over,
})

describe('which collections may be chosen', () => {
  it('reads the axis it was asked for, not another', () => {
    const list: GroupList = {
      'model-projects': [entry({ slug: 'a', name: 'A' })],
      'diagram-collections': [entry({ slug: 'b', name: 'B' })],
    }

    expect(homeOptions(list, 'model-project').map((e) => e.slug)).toEqual(['a'])
    expect(homeOptions(list, 'diagram-collection').map((e) => e.slug)).toEqual(['b'])
    expect(homeOptions(list, 'document-collection')).toEqual([])
  })

  it('leaves out an archived collection, which is where work goes when it stops being current', () => {
    const list: GroupList = {
      'model-projects': [entry({ slug: 'live' }), entry({ slug: 'old', archived: true })],
    }

    expect(homeOptions(list, 'model-project').map((e) => e.slug)).toEqual(['live'])
  })

  it('answers nothing where the axis is absent, rather than throwing', () => {
    expect(homeOptions(null, 'model-project')).toEqual([])
    expect(homeOptions({}, 'model-project')).toEqual([])
  })
})

describe('the home a create form starts on', () => {
  it('is the collection the reader was browsing', () => {
    expect(defaultHome('platform-core', [entry()])).toBe('platform-core')
  })

  it('is blank where that collection is not one of the choices', () => {
    // Browsing an axis this kind is not filed on, or a collection since archived: defaulting to it
    // would set the form to a home the select cannot show and the reader cannot see.
    expect(defaultHome('some-diagram-collection', [entry()])).toBe('')
  })

  it('is blank where nothing was being browsed', () => {
    expect(defaultHome('', [entry()])).toBe('')
  })
})

describe('what a blank choice means on the wire', () => {
  it('is absent on a create, so the caller need not know the slug', () => {
    expect(homeForCreate('')).toBeUndefined()
    expect(homeForCreate('platform-core')).toBe('platform-core')
  })

  it('names the collection on a move, because absent would mean "leave it there"', () => {
    expect(homeForMove('')).toBe(NO_COLLECTION)
    expect(homeForMove('platform-core')).toBe('platform-core')
  })
})
