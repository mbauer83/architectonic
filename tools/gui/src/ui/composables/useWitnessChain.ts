import { ref } from 'vue'
import { Effect } from 'effect'
import type { ModelService } from '../../application/ModelService'
import { walkWitnessChain, witnessChainProse, type ProseSegment } from '../../domain/witnessChainProse'
import type { ConnectionRecord } from '../../domain/schemas/connections'

/** Only the one capability this composable actually needs — narrower than the full
 * `ModelService` both so its real dependency is explicit and so a test can supply a
 * minimal stub instead of the whole service surface. */
export type WitnessChainReadAccess = Pick<ModelService, 'getConnections'>

/** A resolved (or in-flight) witness chain, as consumed by a display component — set only
 * when the selected connection is derived; a real modeled connection has no chain. */
export interface WitnessChainDisplay {
  loading: boolean
  segments: readonly ProseSegment[]
  broken: boolean
}

/** Resolves and renders one derived relationship's witness chain — the real connections
 * that compose it, as prose with every entity name addressable. Shared by
 * `WitnessChainPopover.vue` (the ephemeral layered-exploration flow) and the ephemeral
 * ArchiMate diagram viewer's sidebar, so both render the exact same chain the exact same
 * way. `via_connection_ids` is not guaranteed to arrive in source-to-target traversal
 * order — the derivation engine can extend a composed chain from either end — so
 * resolving each id's real `ConnectionRecord` can't walk the array in order either: it
 * has to search outward from both known endpoints until every id is found. */
export function useWitnessChain(svc: WitnessChainReadAccess) {
  const loading = ref(false)
  const segments = ref<readonly ProseSegment[]>([])
  const broken = ref(false)

  const resolveChainConnections = async (
    sourceEntityId: string,
    targetEntityId: string,
    viaConnectionIds: readonly string[],
  ): Promise<Map<string, ConnectionRecord>> => {
    const remaining = new Set(viaConnectionIds)
    const resolved = new Map<string, ConnectionRecord>()
    const visited = new Set<string>()
    let frontier = [sourceEntityId, targetEntityId]
    while (remaining.size > 0 && frontier.length > 0) {
      const nextFrontier: string[] = []
      for (const entityId of frontier) {
        if (visited.has(entityId)) continue
        visited.add(entityId)
        const connections = await Effect.runPromise(svc.getConnections(entityId, 'any'))
        for (const connection of connections) {
          if (!remaining.has(connection.artifact_id)) continue
          remaining.delete(connection.artifact_id)
          resolved.set(connection.artifact_id, connection)
          const other = connection.source === entityId ? connection.target : connection.source
          if (!visited.has(other)) nextFrontier.push(other)
        }
      }
      frontier = nextFrontier
    }
    return resolved
  }

  const load = async (
    sourceEntityId: string,
    targetEntityId: string,
    viaConnectionIds: readonly string[],
  ): Promise<void> => {
    loading.value = true
    const connectionById = await resolveChainConnections(sourceEntityId, targetEntityId, viaConnectionIds)
    const steps = walkWitnessChain(sourceEntityId, viaConnectionIds, connectionById)
    segments.value = witnessChainProse(steps)
    broken.value = steps.length < viaConnectionIds.length
    loading.value = false
  }

  const clear = (): void => {
    segments.value = []
    broken.value = false
    loading.value = false
  }

  return { loading, segments, broken, load, clear }
}
