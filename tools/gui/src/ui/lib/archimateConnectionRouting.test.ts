import { describe, it, expect } from 'vitest'
import {
  claimInstance,
  drawingCarries,
  endpointOf,
  forgetEntity,
  freeDrawingOn,
  instancesOf,
  releaseConnection,
  releaseInstance,
  routingItems,
} from './archimateConnectionRouting'

const CONN = 'A@1.aa.a---B@1.bb.b@@archimate-realization'

describe('which drawing carries a connection', () => {
  it('is the base drawing when the diagram says nothing', () => {
    // Every diagram authored before routing existed means exactly this, so it must not need one.
    expect(drawingCarries({}, CONN, 'target', null)).toBe(true)
    expect(drawingCarries({}, CONN, 'target', 'occ-b-2')).toBe(false)
  })

  it('follows the entries once there are any', () => {
    const de = { _connections: [{ artifact_id: CONN, 'target-occurrence': 'occ-b-2' }] }

    expect(drawingCarries(de, CONN, 'target', 'occ-b-2')).toBe(true)
    expect(drawingCarries(de, CONN, 'target', null)).toBe(false)
  })

  it('reads the endpoint an entity sits on', () => {
    expect(endpointOf({ source: 'A@1.aa.a', target: 'B@1.bb.b' }, 'B@1.bb.b')).toBe('target')
    expect(endpointOf({ source: 'A@1.aa.a', target: 'B@1.bb.b' }, 'C@1.cc.c')).toBeNull()
  })
})

describe('drawing a connection on a second copy of a cluster', () => {
  it('adds an arrow rather than moving the first one', () => {
    // The layout case: A and B each drawn twice, so each copy reads as a complete unit.
    const de = claimInstance(
      { _connections: [{ artifact_id: CONN }] }, CONN, 'source', 'occ-a-2', 'occ-b-2',
    )

    expect(instancesOf(de, CONN)).toHaveLength(2)
    expect(drawingCarries(de, CONN, 'source', null)).toBe(true)
    expect(drawingCarries(de, CONN, 'source', 'occ-a-2')).toBe(true)
  })

  it('pairs with the first free drawing on the other side, base first', () => {
    const de = { _connections: [{ artifact_id: CONN, 'target-occurrence': 'occ-b-2' }] }

    expect(freeDrawingOn(de, CONN, 'target', [null, 'occ-b-2'])).toBeNull()
    expect(freeDrawingOn({}, CONN, 'target', [null, 'occ-b-2'])).toBe('occ-b-2')
  })

  it('refuses a pairing it already draws, so no two arrows stack', () => {
    const once = claimInstance({}, CONN, 'source', 'occ-a-2', 'occ-b-2')

    expect(instancesOf(claimInstance(once, CONN, 'source', 'occ-a-2', 'occ-b-2'), CONN)).toHaveLength(1)
  })

  it('writes nothing for the first plain arrow between base drawings', () => {
    // That is what an absent entry already says; stating it would be noise in the diagram.
    expect(routingItems(claimInstance({}, CONN, 'source', null, null))).toEqual([])
  })

  it('carries the label opt-ins onto the new arrow — they describe the relation', () => {
    const de = { _connections: [{ artifact_id: CONN, include_multiplicity: true }] }

    const both = claimInstance(de, CONN, 'source', 'occ-a-2', 'occ-b-2')

    expect(instancesOf(both, CONN)[1]).toEqual({
      artifact_id: CONN,
      include_multiplicity: true,
      'source-occurrence': 'occ-a-2',
      'target-occurrence': 'occ-b-2',
    })
  })
})

describe('undrawing', () => {
  it('releases one drawing’s arrow and leaves the others', () => {
    const de = claimInstance({ _connections: [{ artifact_id: CONN }] }, CONN, 'source', 'occ-a-2', 'occ-b-2')

    const after = releaseInstance(de, CONN, 'source', 'occ-a-2')

    expect(instancesOf(after, CONN)).toHaveLength(1)
    expect(drawingCarries(after, CONN, 'source', null)).toBe(true)
  })

  it('releases the connection everywhere at once', () => {
    const de = claimInstance({ _connections: [{ artifact_id: CONN }] }, CONN, 'source', 'occ-a-2', 'occ-b-2')

    expect(instancesOf(releaseConnection(de, CONN), CONN)).toEqual([])
  })
})

describe('forgetting an entity the diagram no longer draws', () => {
  const diagramEntities = {
    occurrence: [
      { id: 'occ-b-2', backing_entity_id: 'B@1.bb.b' },
      { id: 'occ-c-2', backing_entity_id: 'C@1.cc.c' },
    ],
    _connections: [{ artifact_id: CONN, 'target-occurrence': 'occ-b-2' }],
  }

  it('drops every occurrence of it', () => {
    const next = forgetEntity(diagramEntities, 'B@1.bb.b', [CONN])

    expect(next.occurrence).toEqual([{ id: 'occ-c-2', backing_entity_id: 'C@1.cc.c' }])
  })

  it('drops the arrows that went with it', () => {
    expect(routingItems(forgetEntity(diagramEntities, 'B@1.bb.b', [CONN]))).toEqual([])
  })

  it('leaves another entity’s drawings and arrows alone', () => {
    const next = forgetEntity(diagramEntities, 'C@1.cc.c', [])

    expect(next.occurrence).toEqual([{ id: 'occ-b-2', backing_entity_id: 'B@1.bb.b' }])
    expect(routingItems(next)).toEqual([{ artifact_id: CONN, 'target-occurrence': 'occ-b-2' }])
  })

  it('drops an arrow that ran to a dropped drawing even when its connection survives', () => {
    // The connection does not touch the removed entity, so it stays — but an arrow to a drawing
    // nothing declares any more must not be written out.
    const de = {
      occurrence: [{ id: 'occ-b-2', backing_entity_id: 'B@1.bb.b' }],
      _connections: [
        { artifact_id: 'other' },
        { artifact_id: 'other', 'target-occurrence': 'occ-b-2' },
      ],
    }

    expect(routingItems(forgetEntity(de, 'B@1.bb.b', []))).toEqual([])
  })
})
