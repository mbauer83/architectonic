import { computed, ref, type Ref } from 'vue'
import { Effect, Exit } from 'effect'
import type { ModelService } from '../../application/ModelService'
import type {
  DiagramConnection, DiagramContext, EntityContextConnection, EntityDisplayInfo, DiagramContextEntity,
} from '../../domain'
import { stableConnectionId } from '../../domain/artifactId'
import { useDiagramDrawings } from './useDiagramDrawings'

/**
 * Owns the diagram-edit view's whole entity/connection selection & neighbor-discovery
 * state: what's currently included, marked for removal, or newly added; which candidate
 * connections/related entities the discovery search surfaces; and the toggle/add/remove
 * mutations over all of it. Kept as one composable because these pieces are genuinely
 * interdependent — e.g. `relatedEntitiesById` and `refreshDiscovery` both need the same
 * "effective" (included minus removed, plus added) population every other computed here
 * derives from.
 */
export function useDiagramEditSelection(options: {
  svc: ModelService
  diagramType: Ref<string | undefined>
  viewpointSlug: Ref<string | null>
  /** The diagram's own data — which drawings it holds, and which of them owns each connection. */
  typeEntityData: Ref<Record<string, unknown>>
  /** How to write that back; the view owns it, because the write path reads it from there. */
  mergeTypeEntityData: (patch: Record<string, unknown>) => void
}) {
  const { svc, diagramType, viewpointSlug, typeEntityData, mergeTypeEntityData } = options

  // The looser list-row types, deliberately: the context read fills both with its own stricter
  // rows, and a diagram-type editor then replaces the connections with ones it built itself.
  const diagramEntities = ref<DiagramContextEntity[]>([])
  const diagramConnections = ref<DiagramConnection[]>([])
  const includedEntities = ref<EntityDisplayInfo[]>([])
  const allModelConns = ref<Map<string, EntityContextConnection>>(new Map())
  const includedConnIds = ref<Set<string>>(new Set())

  const toRemoveEntityIds = ref<Set<string>>(new Set())
  const toRemoveConnIds = ref<Set<string>>(new Set())
  const entitiesToAdd = ref<EntityDisplayInfo[]>([])
  const selectedNewConnIds = ref<Set<string>>(new Set())
  const expandedConnectionEntityIds = ref<Set<string>>(new Set())
  const expandedRelatedEntityIds = ref<Set<string>>(new Set())

  const includedEntityIds = computed(() => new Set(includedEntities.value.map((e) => e.artifact_id)))
  const toAddEntityIds = computed(() => new Set(entitiesToAdd.value.map((e) => e.artifact_id)))

  const effectiveEntityIds = computed(() => {
    const s = new Set<string>()
    for (const e of includedEntities.value) if (!toRemoveEntityIds.value.has(e.artifact_id)) s.add(e.artifact_id)
    for (const e of entitiesToAdd.value) s.add(e.artifact_id)
    return s
  })

  const drawings = useDiagramDrawings({
    diagramEntities: typeEntityData, write: mergeTypeEntityData, connections: allModelConns,
    drawnEntityIds: effectiveEntityIds,
  })

  const effectiveEntitiesList = computed(() => [
    ...includedEntities.value.filter((e) => !toRemoveEntityIds.value.has(e.artifact_id)),
    ...entitiesToAdd.value,
  ])

  /**
   * Putting a drawing in the box another sits in.
   *
   * The boxes are authored beside this state and need the entity list this holds, so the one
   * operation this needs from them arrives once both exist rather than as a constructor argument.
   */
  const placeBeside = ref<(hostId: string, memberId: string) => void>(() => {})
  const useBoxPlacement = (place: (hostId: string, memberId: string) => void): void => {
    placeBeside.value = place
  }

  /**
   * Connect a drawing that just joined a box to the drawings already inside it.
   *
   * A box should read as a unit, so a new member attaches to what is *in* the box rather than to
   * whichever copy of the same entity sits elsewhere on the picture.
   */
  const wireIntoGroup = (
    entity: EntityDisplayInfo, memberId: string, membersOfBox: readonly string[],
  ): void => {
    const inThisBox = new Set(membersOfBox)
    for (const conn of allModelConns.value.values()) {
      const otherId = conn.source === entity.artifact_id ? conn.target
        : conn.target === entity.artifact_id ? conn.source : null
      if (otherId === null) continue
      const theirDrawing = drawings.drawingsOf(otherId).find(
        (id) => inThisBox.has(id ?? otherId) && (id ?? otherId) !== memberId,
      )
      if (theirDrawing === undefined) continue
      const ours = memberId === entity.artifact_id ? null : memberId
      drawings.drawBetween(conn.artifact_id, entity.artifact_id, ours, theirDrawing)
      if (!isConnIncluded(conn.artifact_id)) toggleConn(conn.artifact_id)
    }
  }

  const baseRows = computed(() =>
    effectiveEntitiesList.value.map((entity) => {
      const isNew = toAddEntityIds.value.has(entity.artifact_id)
      return {
        entity, newInclusion: isNew,
        badgeText: isNew ? 'new' : undefined,
        actionKind: isNew ? 'remove' as const : 'mark-remove' as const,
        actionTitle: isNew ? 'Remove entity from pending additions' : 'Mark entity for removal',
      }
    }),
  )
  const selectionRows = drawings.rowsFor(baseRows)

  /**
   * The entity ids a write names: what survives removal, plus what is being added, plus whatever a
   * diagram-type editor mapped into the diagram's own data itself.
   */
  const finalEntityIds = computed(() => {
    const mapped = typeEntityData.value.entity_ids_mapped
    return [...new Set([
      ...includedEntities.value
        .filter((e) => !toRemoveEntityIds.value.has(e.artifact_id))
        .map((e) => e.artifact_id),
      ...entitiesToAdd.value.map((e) => e.artifact_id),
      ...(Array.isArray(mapped) ? mapped.filter((id): id is string => typeof id === 'string') : []),
    ])]
  })

  const toRemoveEntities = computed(() =>
    includedEntities.value.filter((e) => toRemoveEntityIds.value.has(e.artifact_id)),
  )

  const isConnIncluded = (connId: string): boolean =>
    (includedConnIds.value.has(connId) && !toRemoveConnIds.value.has(connId))
    || selectedNewConnIds.value.has(connId)

  const finalConnIds = computed(() => [
    ...[...includedConnIds.value].filter((id) => !toRemoveConnIds.value.has(id)),
    ...[...selectedNewConnIds.value],
  ])

  const relatedEntitiesById = computed<Record<string, EntityDisplayInfo[]>>(() => {
    const related: Record<string, EntityDisplayInfo[]> = {}
    const seenByEntity = new Map<string, Set<string>>()
    for (const entity of effectiveEntitiesList.value) related[entity.artifact_id] = []
    for (const conn of allModelConns.value.values()) {
      const endpoints: Array<[string, string]> = [[conn.source, conn.target], [conn.target, conn.source]]
      for (const [ownerId, otherId] of endpoints) {
        if (!effectiveEntityIds.value.has(ownerId) || effectiveEntityIds.value.has(otherId)) continue
        if (toRemoveEntityIds.value.has(ownerId)) continue
        const name = ownerId === conn.source ? (conn.target_name ?? otherId) : (conn.source_name ?? otherId)
        const artifactType = ownerId === conn.source ? conn.target_artifact_type : conn.source_artifact_type
        const domain = ownerId === conn.source ? conn.target_domain : conn.source_domain
        const scope = ownerId === conn.source ? conn.target_scope : conn.source_scope
        const seen = seenByEntity.get(ownerId) ?? new Set<string>()
        if (seen.has(otherId)) continue
        seen.add(otherId)
        seenByEntity.set(ownerId, seen)
        related[ownerId].push({
          artifact_id: otherId, name,
          artifact_type: artifactType,
          domain,
          subdomain: '', status: scope, display_alias: '',
          element_type: artifactType, element_label: name, diagram_internal: false,
        })
      }
    }
    for (const entityId of Object.keys(related)) related[entityId].sort((a, b) => a.name.localeCompare(b.name))
    return related
  })

  const toggleConn = (connId: string, entityId?: string, occurrenceId?: string | null): void => {
    const included = isConnIncluded(connId)
    if (entityId) {
      const outcome = drawings.toggleConnectionAt(connId, entityId, occurrenceId ?? null, included)
      if (outcome === 'unchanged') return
    }
    const inIncluded = includedConnIds.value.has(connId)
    const removeItems = included
      ? [...toRemoveConnIds.value, connId]
      : [...toRemoveConnIds.value].filter((id) => id !== connId)
    toRemoveConnIds.value = inIncluded ? new Set(removeItems) : toRemoveConnIds.value
    const newConnItems = included
      ? [...selectedNewConnIds.value].filter((id) => id !== connId)
      : [...selectedNewConnIds.value, connId]
    selectedNewConnIds.value = !inIncluded ? new Set(newConnItems) : selectedNewConnIds.value
  }

  const toggleConnections = (entityId: string): void => {
    const next = new Set(expandedConnectionEntityIds.value)
    if (next.has(entityId)) next.delete(entityId)
    else next.add(entityId)
    expandedConnectionEntityIds.value = next
  }

  const toggleRelated = (key: string): void => {
    const next = new Set(expandedRelatedEntityIds.value)
    if (next.has(key)) next.delete(key)
    else next.add(key)
    expandedRelatedEntityIds.value = next
  }

  const refreshDiscovery = async (): Promise<void> => {
    const exit = await Effect.runPromiseExit(
      svc.discoverDiagramEntities({
        includedEntityIds: [...effectiveEntityIds.value],
        diagramType: diagramType.value,
        viewpoint: viewpointSlug.value ?? undefined,
        maxHops: 1, limit: 20,
      }),
    )
    if (Exit.isSuccess(exit)) {
      allModelConns.value = new Map(exit.value.candidate_connections.map((conn) => [conn.artifact_id, conn]))
    }
  }

  const toggleEntityRemoval = (id: string): void => {
    toRemoveEntityIds.value = toRemoveEntityIds.value.has(id)
      ? new Set([...toRemoveEntityIds.value].filter((x) => x !== id))
      : new Set([...toRemoveEntityIds.value, id])
    expandedConnectionEntityIds.value = new Set([...expandedConnectionEntityIds.value].filter((x) => x !== id))
    expandedRelatedEntityIds.value = new Set([...expandedRelatedEntityIds.value].filter((x) => x !== id))
    void refreshDiscovery()
  }

  const removeToAddEntity = (id: string): void => {
    entitiesToAdd.value = entitiesToAdd.value.filter((e) => e.artifact_id !== id)
    expandedConnectionEntityIds.value = new Set([...expandedConnectionEntityIds.value].filter((x) => x !== id))
    expandedRelatedEntityIds.value = new Set([...expandedRelatedEntityIds.value].filter((x) => x !== id))
    selectedNewConnIds.value = new Set(
      [...selectedNewConnIds.value].filter((cid) => {
        const c = allModelConns.value.get(cid)
        return !(c && (c.source === id || c.target === id))
      }),
    )
    void refreshDiscovery()
  }

  /** From a drawing's Related card the neighbour joins that copy of the cluster — and its box. */
  const addRelatedEntity = async (
    entity: EntityDisplayInfo, viaEntityId: string, occurrenceId: string | null,
  ): Promise<void> => {
    await addEntity(entity)
    placeBeside.value(occurrenceId ?? viaEntityId, entity.artifact_id)
    if (!occurrenceId) return
    for (const id of drawings.connectionsJoining(entity.artifact_id, viaEntityId)) {
      drawings.drawOnlyAt(id, viaEntityId, occurrenceId)
    }
  }

  const handleEntityAction = (entityId: string): void => {
    drawings.forgetEntityDrawings(entityId)
    if (toAddEntityIds.value.has(entityId)) removeToAddEntity(entityId)
    else toggleEntityRemoval(entityId)
  }

  const addEntity = async (entity: EntityDisplayInfo): Promise<void> => {
    if (includedEntityIds.value.has(entity.artifact_id) || toAddEntityIds.value.has(entity.artifact_id)) {
      // Picking one the diagram already draws asks for it to be drawn again — the only thing the
      // choice can mean now the picker no longer hides it.
      drawings.addEntityOccurrence(entity)
      return
    }
    entitiesToAdd.value = [...entitiesToAdd.value, entity]
    await refreshDiscovery()
    const next = new Set(selectedNewConnIds.value)
    for (const conn of allModelConns.value.values()) {
      const touchesAdded = conn.source === entity.artifact_id || conn.target === entity.artifact_id
      const other = conn.source === entity.artifact_id ? conn.target : conn.source
      if (touchesAdded && effectiveEntityIds.value.has(other)) next.add(conn.artifact_id)
    }
    selectedNewConnIds.value = next
  }

  const reset = (): void => {
    toRemoveEntityIds.value = new Set(); toRemoveConnIds.value = new Set()
    entitiesToAdd.value = []; selectedNewConnIds.value = new Set()
    expandedConnectionEntityIds.value = new Set(); expandedRelatedEntityIds.value = new Set()
    includedEntities.value = []; allModelConns.value = new Map(); includedConnIds.value = new Set()
  }

  const populateFromContext = (context: DiagramContext): void => {
    diagramEntities.value = [...context.entities]
    diagramConnections.value = [...context.connections]
    includedEntities.value = context.entities.map((s) => ({
      artifact_id: s.artifact_id, name: s.name, artifact_type: s.artifact_type,
      domain: s.domain, subdomain: s.subdomain, status: s.status,
      display_alias: s.display_alias, element_type: s.artifact_type, element_label: s.name, diagram_internal: false,
    }))
    allModelConns.value = new Map(context.candidate_connections.map((conn) => [conn.artifact_id, conn]))
    const inc = new Set<string>()
    // The diagram declares its connections with full endpoint ids, as authored; the records
    // keyed above name endpoints by stem. Matched on the stem, and the map's own key is what
    // gets recorded, so every later lookup — inclusion, removal marking, the final id set —
    // keeps using one form. Compared verbatim, a declared connection is silently absent from
    // the included set: it still renders, but clicking it can never mark it.
    const keyByStableId = new Map(
      [...allModelConns.value.keys()].map((key) => [stableConnectionId(key), key]),
    )
    for (const cid of context.diagram.connection_ids_used ?? []) {
      const key = keyByStableId.get(stableConnectionId(cid))
      if (key !== undefined) inc.add(key)
    }
    for (const conn of context.connections) inc.add(conn.artifact_id)
    includedConnIds.value = inc
  }

  return {
    diagramEntities, diagramConnections, includedEntities, allModelConns, includedConnIds,
    toRemoveEntityIds, toRemoveConnIds, entitiesToAdd, selectedNewConnIds,
    expandedConnectionEntityIds, expandedRelatedEntityIds,
    includedEntityIds, toAddEntityIds, effectiveEntityIds, effectiveEntitiesList,
    selectionRows, toRemoveEntities, isConnIncluded, finalConnIds, relatedEntitiesById,
    toggleConn, toggleConnections, toggleRelated, toggleEntityRemoval, removeToAddEntity,
    handleEntityAction, refreshDiscovery, addEntity, addRelatedEntity, reset, populateFromContext,
    useBoxPlacement, wireIntoGroup, finalEntityIds,
    addEntityOccurrence: drawings.addEntityOccurrence,
    removeEntityOccurrence: drawings.removeEntityOccurrence,
    drawEntityAgain: drawings.drawEntityAgain,
    drawingForBox: drawings.drawingForBox,
  }
}

export type DiagramEditSelectionApi = ReturnType<typeof useDiagramEditSelection>
