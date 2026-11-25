/**
 * What a canvas session already draws is never offered to be drawn again — including a relation the
 * diagram draws by nesting one element in another, which its context read does not list among the
 * arrows it draws. Without it, the edit panel offered "Draw" on every composition the picture nests.
 */
import { describe, expect, it } from 'vitest'
import type { DiagramContext } from '../..'
import { drawnByEntity, relationsDrawn } from '../canvasComposition'

const context = {
  connections: [{ artifact_id: 'APP@1.a---APP@2.b@@archimate-serving' }],
  diagram: {
    connection_ids_used: ['APP@1.a---APP@2.b@@archimate-serving', 'PRC@3.c---FNC@4.d@@archimate-composition'],
    diagram_entities: {},
  },
  entities: [
    { artifact_id: 'APP@1.a.portal', name: 'Portal', artifact_type: 'application-component' },
    { artifact_id: 'APP@2.b', name: 'Ledger', artifact_type: 'application-component' },
  ],
  suggested_entities: [],
} as unknown as DiagramContext

describe('what a session draws', () => {
  it('holds the arrows, the nested relations, those drawn from the model and those it creates', () => {
    const drawn = relationsDrawn(context, {
      drawnRelations: ['APP@1.a.portal---APP@5.e@@archimate-flow'],
      commands: [{
        op: 'model.relation.create', artifact_id: 'APP@2.b---APP@1.a@@archimate-access',
        description: '', src_multiplicity: '', tgt_multiplicity: '',
      }],
    })
    expect([...drawn].sort()).toEqual([
      'APP@1.a---APP@2.b@@archimate-serving', 'APP@1.a---APP@5.e@@archimate-flow',
      'APP@2.b---APP@1.a@@archimate-access', 'PRC@3.c---FNC@4.d@@archimate-composition',
    ])
  })

  it('names each drawn element by its stable id, the first drawing when there are several', () => {
    const element = (alias: string, key: string) => ({ alias, key })
    const picture = { elements: [element('P', 'APP@1.a'), element('P2', 'APP@1.a'), element('L', 'APP@2.b')], boxes: [] }
    expect(drawnByEntity(context, null, picture as never)).toEqual(new Map([['APP@1.a', 'P'], ['APP@2.b', 'L']]))
  })
})
