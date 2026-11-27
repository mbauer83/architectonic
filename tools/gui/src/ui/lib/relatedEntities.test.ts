import { describe, expect, it } from 'vitest'
import type { EntityContextConnection } from '../../domain'
import { relatedEntitiesOf } from './relatedEntities'

const conn = (
  artifact_id: string, source: string, target: string, names: [string, string],
): EntityContextConnection => ({
  artifact_id, source, target, conn_type: 'archimate-serving', version: '1', status: 'active',
  path: '', content_text: '',
  associated_entities: [], src_multiplicity: '', tgt_multiplicity: '', specializations: [],
  source_name: names[0], target_name: names[1],
  source_artifact_type: 'application-component', target_artifact_type: 'business-process',
  source_domain: 'application', target_domain: 'business',
  source_scope: 'engagement', target_scope: 'enterprise',
  other_entity_id: target, direction: 'outbound',
})

describe('relatedEntitiesOf', () => {
  it('offers each owner the far ends it is not drawn beside yet, once each, by name', () => {
    const related = relatedEntitiesOf(['A', 'B'], new Set(['A', 'B']), [
      conn('c1', 'A', 'Z', ['Alpha', 'Zulu']),
      conn('c2', 'A', 'M', ['Alpha', 'Mike']),
      conn('c3', 'Z', 'A', ['Zulu', 'Alpha']),
      conn('c4', 'A', 'B', ['Alpha', 'Bravo']),
    ])

    expect(related.A.map((entity) => entity.name)).toEqual(['Mike', 'Zulu'])
    expect(related.B).toEqual([])
  })

  it('describes a far end from the side the owner stands on', () => {
    const [seenFromTarget] = relatedEntitiesOf(['P'], new Set(['P']), [conn('c1', 'S', 'P', ['Shop', 'Pay'])]).P

    expect(seenFromTarget).toMatchObject({
      artifact_id: 'S', name: 'Shop', artifact_type: 'application-component', domain: 'application',
      status: 'engagement', diagram_internal: false,
    })
  })

  it('gives every owner an entry, and ignores connections touching none', () => {
    const related = relatedEntitiesOf(['A'], new Set(['A']), [conn('c1', 'X', 'Y', ['X', 'Y'])])

    expect(related).toEqual({ A: [] })
  })
})
