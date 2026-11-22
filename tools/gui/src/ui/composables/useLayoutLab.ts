/**
 * The layout lab's session: the diagram canvas's own arranging session (`useArrangementSession`), with
 * what only a bench needs beside it — breach counts, an explicit widening, and the server's composed
 * picture to compare with. Nothing here is ever written anywhere.
 *
 * The lab takes a picture over exactly as it is: widening is a button of its own, so the effect of
 * each can be judged apart.
 */
import { computed, ref } from 'vue'
import { Effect } from 'effect'
import { labPicture } from '../../adapters/http/HttpLayoutLab'
import { layoutBlock } from '../../domain/layout/lab/labArrangement'
import { countByTier } from '../../domain/layout/lab/labBreaches'
import { widenedArrangement } from '../../domain/layout/lab/labRouting'
import type { ModelService } from '../../application/ModelService'
import { useArrangementSession } from './useArrangementSession'

export type { PassTiming } from './useArrangementSession'

export function useLayoutLab(svc: ModelService) {
  const session = useArrangementSession(
    (shapes) => svc.drawResizedShapes(session.geometry.value?.artifact_id ?? '', shapes),
    (_geometry, automatic) => automatic,
  )
  const loading = ref(false)
  const error = ref<string | null>(null)
  const serverPicture = ref<string | null>(null)
  const serverError = ref<string | null>(null)
  const serverLoading = ref(false)

  const counts = computed(() => countByTier(session.breaches.value))

  const layout = computed(() => {
    const drawn = session.geometry.value
    const now = session.arrangement.value
    return drawn && now ? layoutBlock(drawn, now) : {}
  })

  const load = async (artifactId: string) => {
    loading.value = true
    error.value = null
    serverPicture.value = null
    serverError.value = null
    try {
      session.open(await Effect.runPromise(svc.readLayoutGeometry(artifactId)))
    } catch (failure) {
      session.geometry.value = null
      error.value = failure instanceof Error ? failure.message : String(failure)
    } finally {
      loading.value = false
    }
  }

  /** Open every channel too narrow for its lines, as a first layout is written down: one undoable step. */
  const widen = () => {
    const drawn = session.geometry.value
    const now = session.arrangement.value
    if (drawn && now) session.step({ arrangement: widenedArrangement(drawn, now), byHand: true })
  }

  /** Back to PlantUML's arrangement, with nothing to undo. */
  const reset = () => {
    const drawn = session.geometry.value
    if (!drawn) return
    session.open(drawn)
    serverPicture.value = null
    serverError.value = null
  }

  const askServer = async () => {
    const drawn = session.geometry.value
    if (!drawn) return
    serverLoading.value = true
    serverError.value = null
    try {
      serverPicture.value = await Effect.runPromise(labPicture(drawn.artifact_id, layout.value))
    } catch (failure) {
      serverPicture.value = null
      serverError.value = failure instanceof Error ? failure.message : String(failure)
    } finally {
      serverLoading.value = false
    }
  }

  return {
    ...session, loading, error, counts, layout, serverPicture, serverError, serverLoading,
    load, widen, reset, askServer,
  }
}

export type LayoutLab = ReturnType<typeof useLayoutLab>
