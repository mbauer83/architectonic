/**
 * What a graph surface draws of the relations it holds, with and without the neighbour checkbox.
 */
import { describe, expect, it } from 'vitest'
import { ref } from 'vue'
import { useNeighbourRelations } from '../useNeighbourRelations'

const relations = [
  { source: 'root', target: 'a' },
  { source: 'a', target: 'b' },
]
const nodes = [{ id: 'root', expanded: true }, { id: 'a', expanded: false }, { id: 'b', expanded: false }]

const surface = (offered: boolean) =>
  useNeighbourRelations({ nodes: ref(nodes), edges: ref(relations), rootId: ref('root'), offered: ref(offered) })

describe('useNeighbourRelations', () => {
  it('draws only the explored entities\' relations by default', () => {
    const drawing = surface(true)
    expect(drawing.drawn.value).toEqual([{ source: 'root', target: 'a' }])
    expect(drawing.toggle.value).toEqual({ offered: true, shown: false })
  })

  it('draws the relations between neighbours once asked, and stops when un-asked', () => {
    const drawing = surface(true)
    drawing.show(true)
    expect(drawing.drawn.value).toEqual(relations)
    drawing.show(false)
    expect(drawing.drawn.value).toEqual([{ source: 'root', target: 'a' }])
  })

  it('draws everything where the choice is not offered, as for a viewpoint\'s population', () => {
    const drawing = surface(false)
    expect(drawing.drawn.value).toEqual(relations)
    expect(drawing.toggle.value.offered).toBe(false)
  })
})
