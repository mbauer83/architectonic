import { ref, watch } from 'vue'
import { Effect, Exit } from 'effect'
import type { ConnectionRecord } from '../../../domain'
import { inject } from 'vue'
import { modelServiceKey } from '../../keys'
import type { DtConnType } from './useDatatypeModel'
import { DT_CONN_TYPES } from './useDatatypeModel'

const DT_RELATIONSHIP_KINDS: Record<DtConnType, string> = {
  'dt-association': 'association',
  'dt-aggregation': 'containment',
  'dt-composition': 'containment',
  'dt-generalization': 'generalization',
  'dt-dependency': 'dependency',
}

const DT_SYMMETRIC: Record<DtConnType, boolean> = {
  'dt-association': true,
  'dt-aggregation': false,
  'dt-composition': false,
  'dt-generalization': false,
  'dt-dependency': false,
}

export interface BackingConstraint {
  admissibleTypes: DtConnType[] | null
  backingConnectionFor: (dtType: DtConnType) => ConnectionRecord | undefined
}

export function useDtBackingConstraint(
  getSourceDobId: () => string | undefined,
  getTargetDobId: () => string | undefined,
) {
  const svc = inject(modelServiceKey)!
  const backingConnections = ref<ConnectionRecord[]>([])
  const rkMap = ref<Record<string, string | null>>({})
  const loaded = ref(false)

  const reload = async () => {
    const src = getSourceDobId()
    const tgt = getTargetDobId()
    if (!src || !tgt) {
      backingConnections.value = []
      loaded.value = false
      return
    }
    const [connExit, pairExit] = await Promise.all([
      Effect.runPromiseExit(svc.getConnections(src, 'any')),
      Effect.runPromiseExit(svc.getOntologyPair('data-object', 'data-object')),
    ])
    if (Exit.isSuccess(connExit)) {
      backingConnections.value = connExit.value.filter(
        (c) => (c.source === src && c.target === tgt) || (c.source === tgt && c.target === src),
      )
    }
    if (Exit.isSuccess(pairExit)) {
      rkMap.value = (pairExit.value.relationship_kind_map as Record<string, string | null>) ?? {}
    }
    loaded.value = true
  }

  watch([getSourceDobId, getTargetDobId], () => void reload(), { immediate: true })

  const preferredBackingType = (dtType: DtConnType): string | undefined => {
    const dtKind = DT_RELATIONSHIP_KINDS[dtType]
    const candidates = Object.entries(rkMap.value)
      .filter(([ct, kind]) => kind === dtKind && ct.startsWith('archimate-'))
      .map(([ct]) => ct)
      .sort()
    return candidates[0]
  }

  const admissibleTypes = (): DtConnType[] | null => {
    const src = getSourceDobId()
    const tgt = getTargetDobId()
    if (!src || !tgt || !loaded.value) return null
    if (!backingConnections.value.length) return null

    const result: DtConnType[] = []
    for (const dtType of DT_CONN_TYPES) {
      const dtKind = DT_RELATIONSHIP_KINDS[dtType]
      const symmetric = DT_SYMMETRIC[dtType]
      const matches = backingConnections.value.some((bc) => {
        const bcKind = rkMap.value[bc.conn_type]
        if (bcKind !== dtKind) return false
        if (symmetric) return true
        return bc.source === src && bc.target === tgt
      })
      if (matches) result.push(dtType)
    }
    return result.length ? result : null
  }

  const backingConnectionFor = (dtType: DtConnType, srcDobId?: string, tgtDobId?: string): ConnectionRecord | undefined => {
    const src = srcDobId ?? getSourceDobId()
    const tgt = tgtDobId ?? getTargetDobId()
    if (!src || !tgt) return undefined
    const dtKind = DT_RELATIONSHIP_KINDS[dtType]
    const symmetric = DT_SYMMETRIC[dtType]
    return backingConnections.value.find((bc) => {
      const bcKind = rkMap.value[bc.conn_type]
      if (bcKind !== dtKind) return false
      if (symmetric) return true
      return bc.source === src && bc.target === tgt
    })
  }

  return { admissibleTypes, backingConnectionFor, preferredBackingType, backingConnections, reload }
}
