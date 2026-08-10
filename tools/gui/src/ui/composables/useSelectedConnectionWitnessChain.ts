import { computed, watch, type Ref } from 'vue'
import type { DiagramConnection } from '../../domain'
import type { ModelService } from '../../application/ModelService'
import { useWitnessChain, type WitnessChainDisplay } from './useWitnessChain'

/**
 * The witness chain of whichever connection is currently selected, or nothing.
 *
 * `useWitnessChain` loads a chain when asked for one; deciding *when* to ask, and when the answer is
 * meaningless, is a separate question that the viewpoint view was answering inline. Only a **derived**
 * edge has a composed chain — a real modeled connection was authored, not inferred, so there is no
 * path of witnesses behind it — and that rule belongs with the loading it gates rather than beside a
 * view's pan/zoom and overlay wiring.
 *
 * Both halves are here on purpose: the display value returns null for a non-derived selection, and the
 * watcher clears the loaded chain instead of leaving the previous selection's witnesses on screen
 * under the new one's heading.
 */
export function useSelectedConnectionWitnessChain(
  svc: ModelService,
  selectedConnection: Readonly<Ref<DiagramConnection | null>>,
) {
  const witnessChain = useWitnessChain(svc)

  const display = computed<WitnessChainDisplay | null>(() => {
    const conn = selectedConnection.value
    if (!conn?.certainty) return null
    return {
      loading: witnessChain.loading.value,
      segments: witnessChain.segments.value,
      broken: witnessChain.broken.value,
    }
  })

  watch(selectedConnection, (conn) => {
    if (conn?.certainty && conn.via_connection_ids?.length) {
      void witnessChain.load(conn.source, conn.target, conn.via_connection_ids)
    } else {
      witnessChain.clear()
    }
  })

  return { display }
}
