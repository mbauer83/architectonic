import { describe, expect, it } from 'vitest'
import { membershipWithout } from '../diagramMembership'

describe('a membership less removed entities', () => {
  it('drops them, every connection with an end among them, and their places in groupings', () => {
    const kept = membershipWithout({
      entity_ids: ['A@1.a', 'B@1.b', 'C@1.c'],
      connection_ids: ['A@1.a---B@1.b@@archimate-serving', 'B@1.b---C@1.c@@archimate-flow'],
      authored_groupings: [{ label: 'G', 'entity-ids': ['A@1.a', 'C@1.c'], groups: [{ label: 'H', 'entity-ids': ['C@1.c'] }] }],
    }, new Set(['C@1.c']))
    expect(kept).toEqual({
      entity_ids: ['A@1.a', 'B@1.b'],
      connection_ids: ['A@1.a---B@1.b@@archimate-serving'],
      authored_groupings: [{ label: 'G', 'entity-ids': ['A@1.a'], groups: [{ label: 'H', 'entity-ids': [] }] }],
    })
  })
})
