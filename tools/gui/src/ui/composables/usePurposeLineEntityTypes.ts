import { computed, inject, onMounted, ref, type ComputedRef } from 'vue'
import { Effect } from 'effect'
import { modelServiceKey } from '../keys'
import type { PurposeLineEntityTypes } from '../../domain'
import type { PurposeList } from '../../domain/purposeLines'

/**
 * The entity types a reference in one purpose list may name, as the server's write-help catalogue
 * declares them. Empty until that read answers, and empty if it fails: a picker offers nothing it
 * cannot vouch for, prose stays available, and the verifier (E187) remains the authority on a write.
 */
export function usePurposeLineEntityTypes(list: () => PurposeList): ComputedRef<readonly string[]> {
  const svc = inject(modelServiceKey)!
  const declared = ref<PurposeLineEntityTypes | null>(null)

  onMounted(() => {
    void Effect.runPromise(svc.getWriteHelp())
      .then((help) => { declared.value = help.purpose_line_entity_types })
      .catch(() => {})
  })

  return computed(() => declared.value?.[list()] ?? [])
}
