/**
 * The relation dialog (03·8) offers first the relations the model holds from one element to the other
 * that this diagram does not draw — kept, one is drawn, a diagram change — then the types the ontology
 * permits that the model does not hold — kept, one is created, a model change.
 */
import { describe, expect, it, vi } from 'vitest'
import { computed, ref } from 'vue'
import { Effect } from 'effect'
import type { ModelService } from '../../../application/ModelService'
import type { DiagramContext } from '../../../domain'
import { useCanvasRelation } from '../useCanvasRelation'
import type { DiagramEditing } from '../useDiagramEditing'

const A = 'FNC@1.a.record'
const B = 'BOB@2.b.repository'
const held = (type: string) => ({ artifact_id: `${A}---${B}@@${type}`, source: A, target: B, conn_type: type })

const dialog = (drawnOnDiagram: readonly string[]) => {
  const svc = {
    getOntologyPair: () => Effect.succeed({
      connection_types: ['archimate-access', 'archimate-association'], symmetric: [], relationship_kind_map: {},
    }),
    getConnectionsAmong: () => Effect.succeed([held('archimate-access'), held('archimate-serving')]),
  } as unknown as ModelService
  const editing = { session: { state: ref({ commands: [] }), geometry: ref(null) } } as unknown as DiagramEditing
  const context = { connections: drawnOnDiagram.map((artifact_id) => ({ artifact_id })) } as unknown as DiagramContext
  const members = computed(() => [{ alias: 'a', id: A, type: 'function' }, { alias: 'b', id: B, type: 'business-object' }])
  const [apply, draw] = [vi.fn(), vi.fn()]
  const relation = useCanvasRelation(
    svc, editing, () => context, members, { source: ref('a'), target: ref('') }, () => {}, () => {}, apply, draw,
  )
  return { relation, apply, draw }
}

describe('the relation dialog between two drawn elements', () => {
  it('offers the model relations the diagram does not draw, then the types the model does not hold', async () => {
    const { relation } = dialog([held('archimate-serving').artifact_id])
    await relation.pair('b')
    expect(relation.inModel.value.map((one) => one.type)).toEqual(['archimate-access'])
    expect(relation.options.value).toEqual(['archimate-association'])
    expect(relation.drawing.value).toBe(held('archimate-access').artifact_id)
  })

  it('draws a model relation chosen, and creates a type chosen instead', async () => {
    const { relation, apply, draw } = dialog([])
    await relation.pair('b')
    relation.label.value = 'reads'
    relation.keep()
    expect(draw).toHaveBeenCalledWith(held('archimate-access').artifact_id, expect.objectContaining({ label: 'reads' }))
    relation.drawing.value = ''
    relation.kind.value = 'archimate-association'
    relation.keep()
    expect(apply).toHaveBeenCalledWith(
      expect.objectContaining({ op: 'model.relation.create', artifact_id: `${A}---${B}@@archimate-association` }),
      expect.anything(),
    )
  })
})
