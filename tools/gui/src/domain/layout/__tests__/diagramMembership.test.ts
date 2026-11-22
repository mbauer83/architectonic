import { describe, expect, it } from 'vitest'
import { membershipWithout } from '../diagramMembership'

describe('a membership less removed entities', () => {
  it('drops them, every connection with an end among them, and their places in groupings', () => {
    const kept = membershipWithout({
      entity_ids: ['A@1.a', 'B@1.b', 'C@1.c'],
      connection_ids: ['A@1.a---B@1.b@@archimate-serving', 'B@1.b---C@1.c@@archimate-flow'],
      authored_groupings: [
        { label: 'G', 'entity-ids': ['A@1.a', 'C@1.c'], groups: [{ label: 'H', 'entity-ids': ['C@1.c'] }] },
      ],
    }, new Set(['C@1.c']))
    expect(kept).toEqual({
      entity_ids: ['A@1.a', 'B@1.b'],
      connection_ids: ['A@1.a---B@1.b@@archimate-serving'],
      authored_groupings: [{ label: 'G', 'entity-ids': ['A@1.a'], groups: [{ label: 'H', 'entity-ids': [] }] }],
    })
  })

  // Regression: a layout names an entity by its stable id, and the diagram's lists spell it with its slug.
  // Compared as strings, nothing was removed, the write kept the entity, and the canvas drew it again.
  it('matches an entity named by its stable id against the slugged id the diagram lists', () => {
    const kept = membershipWithout({
      entity_ids: ['DOB@1777293141.4dO6js.global-entity-reference-file', 'A@1.a'],
      connection_ids: ['A@1.a---DOB@1777293141.4dO6js.global-entity-reference-file@@archimate-flow'],
    }, new Set(['DOB@1777293141.4dO6js']))
    expect(kept).toEqual({ entity_ids: ['A@1.a'], connection_ids: [] })
  })
})
