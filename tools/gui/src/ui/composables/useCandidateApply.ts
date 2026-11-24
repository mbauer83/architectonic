/**
 * *Apply to the model…* on a candidate's page: a dry run first, read as what would be written and any
 * refusal, then the apply itself once its reader confirms. The server writes every operation in one
 * write or none, and integrates the candidate when it does; this only sequences the two calls.
 */
import { ref, shallowRef } from 'vue'
import { Effect } from 'effect'
import type { ModelService } from '../../application/ModelService'
import { type ApplyPreview, applyPreview } from '../../domain/candidates/candidateApply'
import { formatEffectError } from '../lib/errors'

export type CandidateApplyAccess = Pick<ModelService, 'applyCandidate'>

export function useCandidateApply(svc: CandidateApplyAccess) {
  /** The dry run being confirmed, for the candidate it was asked about; null when none is open. */
  const preview = shallowRef<(ApplyPreview & { readonly candidate: string }) | null>(null)
  const busy = ref(false)
  const error = ref<string | null>(null)

  const run = async <T>(call: () => Promise<T>): Promise<T | null> => {
    busy.value = true
    try {
      const answer = await call()
      error.value = null
      return answer
    } catch (failure) {
      error.value = formatEffectError(failure)
      return null
    } finally {
      busy.value = false
    }
  }

  /** Ask what applying *id* would write; nothing is written. */
  const open = async (id: string): Promise<void> => {
    preview.value = null
    const answer = await run(() => Effect.runPromise(svc.applyCandidate(id, true)))
    if (answer) preview.value = { candidate: id, ...applyPreview(answer) }
  }

  const close = (): void => {
    preview.value = null
    error.value = null
  }

  /** Apply the previewed candidate; answers whether it was integrated. A refusal stays open, saying why. */
  const confirm = async (): Promise<boolean> => {
    const id = preview.value?.candidate
    if (!id) return false
    const answer = await run(() => Effect.runPromise(svc.applyCandidate(id, false)))
    if (!answer?.integrated) return false
    preview.value = null
    return true
  }

  return { preview, busy, error, open, close, confirm }
}

export type CandidateApply = ReturnType<typeof useCandidateApply>
