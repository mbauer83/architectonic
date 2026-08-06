import { computed, type Ref } from 'vue'
import type { EntityContextConnection, EntityDisplayInfo } from '../../domain'
import {
  addOccurrence, addOccurrenceFor, occurrenceOrdinal, occurrencesOf, removeOccurrence,
} from '../lib/archimateOccurrences'
import {
  claimInstance, drawingCarries, endpointOf, forgetEntity, freeDrawingOn, instancesOf,
  releaseConnection, releaseInstance, withBaseInstance, type Drawing,
} from '../lib/archimateConnectionRouting'

/**
 * How many times a diagram draws each entity, and which drawings its arrows run between.
 *
 * Create and edit both author this, and their bookkeeping around it differs — create keeps one set
 * of included connection ids, edit keeps pending add/remove sets against a saved diagram — but the
 * *drawing* rules are identical, and writing them twice is how the two surfaces drift. So this owns
 * the rules and hands back what the caller should do to its own inclusion state, rather than
 * reaching into it.
 */
export type ToggleOutcome = 'include' | 'exclude' | 'unchanged'

/** The drawing an entity has before any copy is made — what "no occurrence named" resolves to. */
const BASE_DRAWING: Drawing = null

export function useDiagramDrawings(options: {
  diagramEntities: Ref<Record<string, unknown>>
  write: (next: Record<string, unknown>) => void
  connections: Ref<Map<string, EntityContextConnection>>
  /** What the diagram already draws — how a first drawing is told from a further one. */
  drawnEntityIds: Ref<ReadonlySet<string>>
}) {
  const { diagramEntities, write, connections, drawnEntityIds } = options

  /** Every drawing of an entity, base first — the order a free one is looked for in. */
  const drawingsOf = (entityId: string): Drawing[] => [
    BASE_DRAWING,
    ...occurrencesOf(diagramEntities.value, entityId).map((occurrence) => occurrence.id),
  ]

  const addEntityOccurrence = (entity: EntityDisplayInfo): void => {
    write(addOccurrence(diagramEntities.value, entity))
  }

  /** Its arrows are not lost: they lose their claim and are offered on every drawing again. */
  const removeEntityOccurrence = (occurrenceId: string): void => {
    write(removeOccurrence(diagramEntities.value, occurrenceId))
  }

  /** Draw an entity again for a box's sake, handing back the drawing the box should hold. */
  const drawEntityAgain = (entity: EntityDisplayInfo): string => {
    const { diagramEntities: next, occurrenceId } = addOccurrenceFor(diagramEntities.value, entity)
    write(next)
    return occurrenceId
  }

  /**
   * The drawing a box should hold for this entity, and whether the diagram gained it just now.
   *
   * Putting an entity in a box means drawing it *there*. A drawing already on the picture stays
   * where it is — a box must not silently relocate it — so the box gets a new one, which is what
   * makes it appear as its own row. An entity the diagram does not draw yet has nothing to leave
   * behind, so its first drawing goes in the box rather than a loose copy being made to duplicate.
   */
  const drawingForBox = (entity: EntityDisplayInfo): { memberId: string, isNew: boolean } =>
    drawnEntityIds.value.has(entity.artifact_id)
      ? { memberId: drawEntityAgain(entity), isNew: false }
      : { memberId: entity.artifact_id, isNew: true }

  /**
   * Draw or undraw a connection at one drawing, and say what that means for inclusion.
   *
   * Undrawing removes only that arrow; `'exclude'` comes back only when it was the last one.
   * Drawing it claims a free drawing on the far side — base first, so a duplicated cluster's second
   * copy pairs with the far endpoint's second copy without the author saying so. The implicit
   * base-to-base arrow is written down first, or claiming for a second drawing would *move* the
   * first rather than add one. `'unchanged'` means the far endpoint had no drawing left to pair
   * with, so there was no arrow to add.
   */
  const toggleConnectionAt = (
    connectionId: string, entityId: string, drawing: Drawing, isIncluded: boolean,
  ): ToggleOutcome => {
    const conn = connections.value.get(connectionId)
    const endpoint = conn ? endpointOf(conn, entityId) : null
    if (!conn || !endpoint) return isIncluded ? 'exclude' : 'include'
    const de = diagramEntities.value
    if (isIncluded && drawingCarries(de, connectionId, endpoint, drawing)) {
      const released = releaseInstance(de, connectionId, endpoint, drawing)
      const remaining = instancesOf(released, connectionId).length
      write(remaining ? released : releaseConnection(released, connectionId))
      return remaining ? 'unchanged' : 'exclude'
    }
    const otherEnd = endpoint === 'source' ? 'target' : 'source'
    const otherId = endpoint === 'source' ? conn.target : conn.source
    const withBase = isIncluded ? withBaseInstance(de, connectionId) : de
    const free = freeDrawingOn(withBase, connectionId, otherEnd, drawingsOf(otherId))
    if (free === undefined) return 'unchanged'
    write(claimInstance(withBase, connectionId, endpoint, drawing, free))
    return isIncluded ? 'unchanged' : 'include'
  }

  /**
   * Draw a connection at exactly one drawing, replacing whatever the diagram said before.
   *
   * What pulling a neighbour in from an occurrence's Related card means: the neighbour joins *that*
   * copy of the cluster and no other. Toggling could not express it — including the entity already
   * put the connection on the base drawing implicitly, and claiming for the occurrence on top of
   * that *added* an arrow rather than placing the only one, so the relation showed at the parent.
   */
  const drawBetween = (
    connectionId: string, entityId: string, drawing: Drawing, otherDrawing: Drawing,
  ): void => {
    const conn = connections.value.get(connectionId)
    const endpoint = conn ? endpointOf(conn, entityId) : null
    if (!conn || !endpoint) return
    const cleared = releaseConnection(diagramEntities.value, connectionId)
    write(claimInstance(cleared, connectionId, endpoint, drawing, otherDrawing))
  }

  const drawOnlyAt = (connectionId: string, entityId: string, drawing: Drawing): void => {
    const conn = connections.value.get(connectionId)
    const endpoint = conn ? endpointOf(conn, entityId) : null
    if (!conn || !endpoint) return
    const otherEnd = endpoint === 'source' ? 'target' : 'source'
    const otherId = endpoint === 'source' ? conn.target : conn.source
    const cleared = releaseConnection(diagramEntities.value, connectionId)
    const free = freeDrawingOn(cleared, connectionId, otherEnd, drawingsOf(otherId))
    drawBetween(connectionId, entityId, drawing, free ?? null)
  }

  /** The connections joining a neighbour to the drawing whose Related card offered it. */
  const connectionsJoining = (entityId: string, viaEntityId: string): string[] =>
    [...connections.value.values()]
      .filter((conn) =>
        (conn.source === entityId && conn.target === viaEntityId)
        || (conn.target === entityId && conn.source === viaEntityId))
      .map((conn) => conn.artifact_id)

  /**
   * Forget an entity's drawings and the arrows that ran to them.
   *
   * The diagram's own data outlives the entity list, so without this a removed entity's extra
   * drawings stayed listed under an entity the diagram no longer contained.
   */
  const forgetEntityDrawings = (entityId: string): void => {
    const touching = [...connections.value.values()]
      .filter((conn) => conn.source === entityId || conn.target === entityId)
      .map((conn) => conn.artifact_id)
    write(forgetEntity(diagramEntities.value, entityId, touching))
  }

  /**
   * One row per *drawing*: the entity's base row, then one for each additional occurrence.
   *
   * An occurrence exists to carry different connections, so it needs somewhere to edit them —
   * beside the base drawing's row, rather than a separate panel that could only add and remove
   * copies.
   */
  const rowsFor = <T extends { entity: EntityDisplayInfo }>(rows: Ref<readonly T[]>) =>
    computed(() =>
      rows.value.flatMap((row) => [
        { ...row, occurrenceId: BASE_DRAWING },
        ...occurrencesOf(diagramEntities.value, row.entity.artifact_id).map((occurrence, index) => ({
          entity: row.entity,
          actionKind: 'remove' as const,
          occurrenceId: occurrence.id,
          occurrenceOrdinal: occurrenceOrdinal(index),
        })),
      ]),
    )

  return {
    drawingsOf, addEntityOccurrence, removeEntityOccurrence, drawEntityAgain, drawingForBox,
    toggleConnectionAt, drawOnlyAt, drawBetween, connectionsJoining, forgetEntityDrawings, rowsFor,
  }
}
