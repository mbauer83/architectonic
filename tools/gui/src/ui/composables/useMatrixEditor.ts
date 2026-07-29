import { ref, computed, watch, inject } from 'vue'
import { Effect } from 'effect'
import { modelServiceKey } from '../keys'
import type { EntityDisplayInfo, EntityContextConnection } from '../../domain'

export interface MatrixConnTypeConfig { conn_type: string; active: boolean }

export function useMatrixEditor(opts?: { toEntityIds?: () => string[] }) {
  const svc = inject(modelServiceKey)!

  const entityOrder = ref<EntityDisplayInfo[]>([])
  const connTypeConfigs = ref<MatrixConnTypeConfig[]>([])
  const allModelConns = ref<Map<string, EntityContextConnection>>(new Map())

  const includedEntityIds = computed(() => new Set(entityOrder.value.map(e => e.artifact_id)))

  const toEntityIdSet = computed(() => {
    const toIds = opts?.toEntityIds?.()
    return toIds?.length ? new Set(toIds) : includedEntityIds.value
  })

  const allDiscoveryIds = computed(() => {
    const toIds = opts?.toEntityIds?.() ?? []
    return [...entityOrder.value.map(e => e.artifact_id), ...toIds.filter(id => !includedEntityIds.value.has(id))]
  })

  const availableConnTypes = computed(() => {
    const types = new Set<string>()
    for (const conn of allModelConns.value.values()) {
      if (includedEntityIds.value.has(conn.source) && toEntityIdSet.value.has(conn.target)) {
        types.add(conn.conn_type)
      }
      if (includedEntityIds.value.has(conn.target) && toEntityIdSet.value.has(conn.source)) {
        types.add(conn.conn_type)
      }
    }
    return types
  })

  watch(availableConnTypes, (current) => {
    if (allModelConns.value.size === 0) return
    const next = connTypeConfigs.value.filter(c => current.has(c.conn_type))
    const existing = new Set(next.map(c => c.conn_type))
    for (const ct of [...current].sort()) {
      if (!existing.has(ct)) next.push({ conn_type: ct, active: true })
    }
    connTypeConfigs.value = next
  })

  const _buildRelatedMap = (
    ownerIds: string[], ownerIdSet: Set<string>,
  ): Record<string, EntityDisplayInfo[]> => {
    const related: Record<string, EntityDisplayInfo[]> = {}
    const seenByEntity = new Map<string, Set<string>>()
    for (const id of ownerIds) related[id] = []
    for (const conn of allModelConns.value.values()) {
      for (const [ownerId, otherId] of [[conn.source, conn.target], [conn.target, conn.source]] as [string, string][]) {
        if (!ownerIdSet.has(ownerId) || ownerIdSet.has(otherId)) continue
        const name = ownerId === conn.source ? (conn.target_name ?? otherId) : (conn.source_name ?? otherId)
        const artifactType = ownerId === conn.source ? conn.target_artifact_type : conn.source_artifact_type
        const domain = ownerId === conn.source ? conn.target_domain : conn.source_domain
        const seen = seenByEntity.get(ownerId) ?? new Set<string>()
        if (seen.has(otherId)) continue
        seen.add(otherId)
        seenByEntity.set(ownerId, seen)
        related[ownerId].push({
          artifact_id: otherId, name,
          artifact_type: artifactType,
          domain: domain,
          subdomain: '', status: '', display_alias: '',
          element_type: artifactType, element_label: name, diagram_internal: false,
        })
      }
    }
    for (const id of Object.keys(related)) related[id].sort((a, b) => a.name.localeCompare(b.name))
    return related
  }

  const relatedEntitiesById = computed<Record<string, EntityDisplayInfo[]>>(() =>
    _buildRelatedMap(entityOrder.value.map(e => e.artifact_id), includedEntityIds.value),
  )

  const toRelatedEntitiesById = computed<Record<string, EntityDisplayInfo[]>>(() => {
    const toIds = opts?.toEntityIds?.() ?? []
    return toIds.length ? _buildRelatedMap(toIds, new Set(toIds)) : {}
  })

  const connCountsByType = computed<Record<string, number>>(() => {
    const counts: Record<string, number> = {}
    for (const conn of allModelConns.value.values()) {
      const forward = includedEntityIds.value.has(conn.source) && toEntityIdSet.value.has(conn.target)
      const backward = includedEntityIds.value.has(conn.target) && toEntityIdSet.value.has(conn.source)
      if (forward || backward) {
        counts[conn.conn_type] = (counts[conn.conn_type] ?? 0) + 1
      }
    }
    return counts
  })

  const refreshDiscovery = async (query = '') => {
    const discovery = await Effect.runPromise(
      svc.discoverDiagramEntities({
        includedEntityIds: allDiscoveryIds.value,
        query: query || undefined,
        maxHops: 1,
        limit: 20,
      }),
    ).catch(() => null)
    if (!discovery) return
    allModelConns.value = new Map(discovery.candidate_connections.map((c) => [c.artifact_id, c]))
  }

  const addEntity = async (entity: EntityDisplayInfo) => {
    if (includedEntityIds.value.has(entity.artifact_id)) return
    entityOrder.value = [...entityOrder.value, entity]
    await refreshDiscovery()
  }

  const removeEntity = (id: string) => {
    entityOrder.value = entityOrder.value.filter(e => e.artifact_id !== id)
  }

  const reorderEntities = (fromIdx: number, toIdx: number) => {
    const arr = [...entityOrder.value]
    const [moved] = arr.splice(fromIdx, 1)
    arr.splice(toIdx, 0, moved)
    entityOrder.value = arr
  }

  const toggleConnType = (connType: string) => {
    connTypeConfigs.value = connTypeConfigs.value.map(c =>
      c.conn_type === connType ? { ...c, active: !c.active } : c,
    )
  }

  const reorderConnTypes = (fromIdx: number, toIdx: number) => {
    const arr = [...connTypeConfigs.value]
    const [moved] = arr.splice(fromIdx, 1)
    arr.splice(toIdx, 0, moved)
    connTypeConfigs.value = arr
  }

  return {
    entityOrder,
    connTypeConfigs,
    allModelConns,
    includedEntityIds,
    availableConnTypes,
    relatedEntitiesById,
    toRelatedEntitiesById,
    connCountsByType,
    refreshDiscovery,
    addEntity,
    removeEntity,
    reorderEntities,
    toggleConnType,
    reorderConnTypes,
  }
}
