import { describe, expect, it } from 'vitest'
import type { GroupEntry, GroupList } from '../../domain/schemas/groups'
import { projectsByUse } from './canvasProjects'

const project = (slug: string, archived = false): GroupEntry => ({
  slug, id: `GRP@1.${slug}`, name: slug, description: '', order: 0, archived, default: false,
  meta_ontology: '', type_filter: [], member_count: 0,
})

describe('the projects a new element may be filed into', () => {
  it('lists those holding most of the diagram first, ties in the server order, archives left out', () => {
    const list: GroupList = {
      'model-projects': [project('alpha'), project('beta'), project('gamma'), project('old', true)],
    }
    const drawn = ['gamma', 'beta', 'gamma', undefined, 'old', 'old', 'old']
    expect(projectsByUse(list, drawn).map((one) => one.slug)).toEqual(['gamma', 'beta', 'alpha'])
  })

  it('reads the model projects of a listing, and nothing from another axis', () => {
    const list: GroupList = { 'diagram-collections': [project('views')] }
    expect(projectsByUse(list, [])).toEqual([])
    expect(projectsByUse(null, [])).toEqual([])
  })
})
