/**
 * A form's default name for a new document, made free before it is offered: the server answers the name
 * proposed, or it numbered "(2)", "(3)", … where a document of the type already has it — the rule a
 * create refuses a taken name by, asked rather than worked out again here. Until it answers, and where it
 * cannot, the proposed name stands; the create still refuses a taken one, in its own words.
 */
import { computed, ref, watch } from 'vue'
import { Effect } from 'effect'
import type { ModelService } from '../../application/ModelService'

export type FreeTitleAccess = Pick<ModelService, 'freeDocumentTitle'>

export function useFreeDocumentTitle(svc: FreeTitleAccess, docType: string, proposed: () => string) {
  /** The free name, for the proposal it answers. */
  const answered = ref<{ readonly asked: string; readonly title: string } | null>(null)
  watch(proposed, async (asked) => {
    if (!asked) return
    const free = await Effect.runPromise(svc.freeDocumentTitle(docType, asked)).catch(() => null)
    if (free && proposed() === asked) answered.value = { asked, title: free.title }
  }, { immediate: true })
  return computed(() => {
    const asked = proposed()
    return answered.value?.asked === asked ? answered.value.title : asked
  })
}
