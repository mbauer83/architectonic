import { computed, ref, type Ref } from 'vue'
import { Effect, Exit } from 'effect'
import type { ModelService } from '../../application/ModelService'
import type {
  DiagramConnection, DiagramContext, EntityContextConnection, EntityDisplayInfo, EntitySummary,
} from '../../domain'
import { stableConnectionId } from '../../domain/artifactId'

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
}) {
  const { svc, diagramType, viewpointSlug } = options

  // The looser list-row types, deliberately: the context read fills both with its own stricter
  // rows, and a diagram-type editor then replaces the connections with ones it built itself.
  const diagramEntities = ref<EntitySummary[]>([])
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

  const effectiveEntitiesList = computed(() => [
    ...includedEntities.value.filter((e) => !toRemoveEntityIds.value.has(e.artifact_id)),
    ...entitiesToAdd.value,
  ])

  const selectionRows = computed(() =>
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

  const toggleConn = (connId: string): void => {
    const included = isConnIncluded(connId)
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

  const toggleRelated = (entityId: string): void => {
    const next = new Set(expandedRelatedEntityIds.value)
    if (next.has(entityId)) next.delete(entityId)
    else next.add(entityId)
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

  const handleEntityAction = (entityId: string): void =>
    toAddEntityIds.value.has(entityId) ? removeToAddEntity(entityId) : toggleEntityRemoval(entityId)

  const addEntity = async (entity: EntityDisplayInfo): Promise<void> => {
    if (includedEntityIds.value.has(entity.artifact_id) || toAddEntityIds.value.has(entity.artifact_id)) return
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
    handleEntityAction, refreshDiscovery, addEntity, reset, populateFromContext,
  }
}

export type DiagramEditSelectionApi = ReturnType<typeof useDiagramEditSelection>
