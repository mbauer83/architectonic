import { inject, ref } from 'vue'
import { Effect } from 'effect'
import { modelServiceKey } from '../keys'
import type { WizardSuggestion, useWizardSession } from './useWizardSession'
import { readErrorMessage } from '../lib/errors'

/**
 * Commits a suggestion as a real connection (dry-run implied by the underlying `addConnection`
 * port already being the verified write path) and records it in the session. Shared by
 * `WizardEntityStage.vue` (accepting a freshly-surfaced suggestion) and the wizard hub's
 * review-later list (accepting a previously-deferred one) — same commit sequence, different
 * removal call once it succeeds (`dismissSuggestion` vs. `resolveReviewLater`).
 */
export function useSuggestionCommit(session: ReturnType<typeof useWizardSession>) {
  const svc = inject(modelServiceKey)!
  const busy = ref(false)
  const error = ref<string | null>(null)

  const accept = (suggestion: WizardSuggestion, onCommitted: (id: string) => void) => {
    busy.value = true
    error.value = null
    void Effect.runPromise(svc.addConnection({
      source_entity: suggestion.sourceId,
      connection_type: suggestion.connectionType,
      target_entity: suggestion.targetId,
      dry_run: false,
    })).then((result) => {
      busy.value = false
      if (!result.wrote) { error.value = result.content ?? 'Verification failed'; return }
      session.recordConnectionCreated({
        sourceId: suggestion.sourceId, connectionType: suggestion.connectionType,
        targetId: suggestion.targetId, summary: suggestion.summary,
      })
      onCommitted(suggestion.id)
    }).catch((err: unknown) => {
      busy.value = false
      error.value = readErrorMessage(err)
    })
  }

  return { accept, busy, error }
}
