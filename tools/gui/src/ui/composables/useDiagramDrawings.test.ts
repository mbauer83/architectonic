import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useDiagramDrawings } from './useDiagramDrawings'
import { instancesOf, drawingCarries } from '../lib/archimateConnectionRouting'
import type { EntityContextConnection } from '../../domain'

const A = 'PRC@1.aa.a'
const NEIGHBOUR = 'BOB@1.bb.b'
const CONN = `${A}---${NEIGHBOUR}@@archimate-access`

const setup = (diagramEntities: Record<string, unknown> = {}, drawn: string[] = []) => {
  const de = ref(diagramEntities)
  const connections = ref(new Map<string, EntityContextConnection>([
    [CONN, { artifact_id: CONN, source: A, target: NEIGHBOUR, conn_type: 'archimate-access' } as EntityContextConnection],
  ]))
  const drawnEntityIds = ref<ReadonlySet<string>>(new Set(drawn))
  return {
    de,
    drawings: useDiagramDrawings({
      diagramEntities: de, write: (next) => { de.value = next }, connections, drawnEntityIds,
    }),
  }
}

describe('pulling a neighbour in from one occurrence', () => {
  it('draws the connection only at that occurrence, never at the parent', () => {
    // The defect: including the entity had already put the connection on the base drawing
    // implicitly, and claiming for the occurrence on top of that added a second arrow — so the
    // relation showed up at the parent entity, which is not what the Related card offered.
    const { de, drawings } = setup({ occurrence: [{ id: 'a-2', backing_entity_id: A }] })

    drawings.drawOnlyAt(CONN, A, 'a-2')

    expect(instancesOf(de.value, CONN)).toEqual([{ artifact_id: CONN, 'source-occurrence': 'a-2' }])
    expect(drawingCarries(de.value, CONN, 'source', null)).toBe(false)
    expect(drawingCarries(de.value, CONN, 'source', 'a-2')).toBe(true)
  })

  it('replaces an arrow the diagram had drawn elsewhere rather than adding to it', () => {
    const { de, drawings } = setup({
      occurrence: [{ id: 'a-2', backing_entity_id: A }, { id: 'a-3', backing_entity_id: A }],
      _connections: [{ artifact_id: CONN, 'source-occurrence': 'a-3' }],
    })

    drawings.drawOnlyAt(CONN, A, 'a-2')

    expect(instancesOf(de.value, CONN)).toHaveLength(1)
    expect(drawingCarries(de.value, CONN, 'source', 'a-2')).toBe(true)
  })

  it('leaves the diagram alone for a connection it does not hold', () => {
    const { de, drawings } = setup()

    drawings.drawOnlyAt('not-a-connection', A, 'a-2')

    expect(instancesOf(de.value, 'not-a-connection')).toEqual([])
  })
})

describe('drawing an entity again', () => {
  it('hands back the new drawing and records it', () => {
    const { de, drawings } = setup()

    const id = drawings.drawEntityAgain({ artifact_id: A, name: 'A', display_alias: 'PRC_A' } as never)

    expect(drawings.drawingsOf(A)).toEqual([null, id])
    expect(de.value.occurrence).toHaveLength(1)
  })

  it('forgets an entity’s drawings and the arrows that ran to them', () => {
    const { de, drawings } = setup({
      occurrence: [{ id: 'a-2', backing_entity_id: A }],
      _connections: [{ artifact_id: CONN, 'source-occurrence': 'a-2' }],
    })

    drawings.forgetEntityDrawings(A)

    expect(de.value.occurrence).toEqual([])
    expect(instancesOf(de.value, CONN)).toEqual([])
  })
})

describe('joining a box', () => {
  it('connects a new member to the drawing inside that box, not to a copy elsewhere', () => {
    // The box should read as a unit: what is in it connects to what is in it.
    const { de, drawings } = setup({ occurrence: [{ id: 'a-2', backing_entity_id: A }] })

    drawings.drawBetween(CONN, NEIGHBOUR, null, 'a-2')

    expect(instancesOf(de.value, CONN)).toEqual([{ artifact_id: CONN, 'source-occurrence': 'a-2' }])
  })

  it('replaces whatever the connection said before rather than adding an arrow', () => {
    const { de, drawings } = setup({
      occurrence: [{ id: 'a-2', backing_entity_id: A }, { id: 'a-3', backing_entity_id: A }],
      _connections: [{ artifact_id: CONN, 'source-occurrence': 'a-3' }],
    })

    drawings.drawBetween(CONN, NEIGHBOUR, null, 'a-2')

    expect(instancesOf(de.value, CONN)).toHaveLength(1)
    expect(drawingCarries(de.value, CONN, 'source', 'a-2')).toBe(true)
  })
})

describe('which drawing a box gets', () => {
  it('gives the box its own drawing when the diagram already draws the entity', () => {
    // The drawing already on the picture stays put: a box must not silently relocate it.
    const { de, drawings } = setup({}, [A])

    const { memberId, isNew } = drawings.drawingForBox({ artifact_id: A, name: 'A', display_alias: 'PRC_A' } as never)

    expect(isNew).toBe(false)
    expect(memberId).not.toBe(A)
    expect(de.value.occurrence).toHaveLength(1)
  })

  it('puts the first drawing in the box when the diagram does not draw it yet', () => {
    // Nothing to leave behind, so a loose copy made only to duplicate it would be noise.
    const { de, drawings } = setup()

    const { memberId, isNew } = drawings.drawingForBox({ artifact_id: A, name: 'A', display_alias: 'PRC_A' } as never)

    expect(isNew).toBe(true)
    expect(memberId).toBe(A)
    expect(de.value.occurrence ?? []).toHaveLength(0)
  })
})
