import { describe, it, expect } from 'vitest'
import { connectionsByType } from './rowConnections'
import { claimInstance } from './archimateConnectionRouting'
import type { EntityContextConnection } from '../../domain'

const A = 'PRC@1.aa.a'
const B = 'BOB@1.bb.b'
const CONN = `${A}---${B}@@archimate-access`

const conn = {
  artifact_id: CONN, source: A, target: B, conn_type: 'archimate-access',
  source_name: 'A', target_name: 'B',
} as EntityContextConnection

const ask = (options: {
  entityId?: string
  drawing?: string | null
  included?: boolean
  diagramEntities?: Record<string, unknown>
}) => connectionsByType({
  entityId: options.entityId ?? A,
  drawing: options.drawing ?? null,
  candidates: [conn],
  includedEntityIds: new Set([A, B]),
  includedConnectionIds: new Set(options.included === false ? [] : [CONN]),
  diagramEntities: options.diagramEntities ?? {},
  nameOf: (id) => (id === A ? 'A' : 'B'),
})

const bucket = (result: ReturnType<typeof connectionsByType>) =>
  result.length ? result[0][1] : { included: [], excluded: [] }

describe('what one drawing of an entity offers', () => {
  it('shows an included connection on the base drawing when nothing is routed', () => {
    expect(bucket(ask({})).included).toHaveLength(1)
  })

  it('shows an unincluded connection as available', () => {
    expect(bucket(ask({ included: false })).excluded).toHaveLength(1)
  })

  it('hides a connection from a drawing that cannot take it', () => {
    // B is drawn once and already has the arrow, so A's second drawing has nothing to pair with —
    // two arrows into the same B would be the same fact twice.
    const de = { occurrence: [{ id: 'a-2', backing_entity_id: A }] }

    expect(bucket(ask({ drawing: 'a-2', diagramEntities: de }))).toEqual({ included: [], excluded: [] })
  })

  it('offers it to a second drawing once the far endpoint is drawn twice', () => {
    // The layout case: both duplicated, so each copy can carry its own arrow.
    const de = {
      occurrence: [
        { id: 'a-2', backing_entity_id: A },
        { id: 'b-2', backing_entity_id: B },
      ],
    }

    expect(bucket(ask({ drawing: 'a-2', diagramEntities: de })).excluded).toHaveLength(1)
  })

  it('shows it as drawn on the copy that carries it, and offers it nowhere else', () => {
    const de = claimInstance(
      {
        occurrence: [
          { id: 'a-2', backing_entity_id: A },
          { id: 'b-2', backing_entity_id: B },
        ],
      },
      CONN, 'source', 'a-2', 'b-2',
    )

    expect(bucket(ask({ drawing: 'a-2', diagramEntities: de })).included).toHaveLength(1)
    // The base row does not show it as drawn — that arrow belongs to the other copy — but it may
    // still claim one, because both base drawings are unspoken for and pairing them is legal.
    const base = bucket(ask({ drawing: null, diagramEntities: de }))
    expect(base.included).toHaveLength(0)
    expect(base.excluded).toHaveLength(1)
  })

  it('says nothing about an entity the diagram does not draw', () => {
    expect(connectionsByType({
      entityId: 'GONE@1.cc.c', drawing: null, candidates: [conn],
      includedEntityIds: new Set([A, B]), includedConnectionIds: new Set([CONN]),
      diagramEntities: {}, nameOf: () => undefined,
    })).toEqual([])
  })

  it('skips a connection whose far end the diagram does not draw', () => {
    expect(connectionsByType({
      entityId: A, drawing: null, candidates: [conn],
      includedEntityIds: new Set([A]), includedConnectionIds: new Set([CONN]),
      diagramEntities: {}, nameOf: () => undefined,
    })).toEqual([])
  })
})
