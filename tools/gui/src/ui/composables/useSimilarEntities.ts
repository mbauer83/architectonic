import { ref, watch, type Ref } from 'vue'
import type { EntityDisplayInfo } from '../../domain'

export type SimilarEntitySearch =
  (query: string, entityType: string) => Promise<readonly EntityDisplayInfo[]>

/**
 * Debounced same-type live search over the name being typed — the wizard's "reuse instead of
 * duplicating" surface (WU-B4.3): while a user types "Customer Portal" into a create form, any
 * existing entity of that type with a similar name is offered for reuse before a duplicate is
 * born. Search failures degrade to "no matches" — dedupe hints must never block creation.
 */
export const useSimilarEntities = (
  search: SimilarEntitySearch,
  entityType: () => string,
  name: Ref<string>,
  { debounceMs = 300, minChars = 2 } = {},
) => {
  const matches = ref<readonly EntityDisplayInfo[]>([])
  let timer: ReturnType<typeof setTimeout> | undefined
  let generation = 0

  watch(name, (value) => {
    if (timer !== undefined) clearTimeout(timer)
    const query = value.trim()
    if (query.length < minChars) { matches.value = []; return }
    const gen = ++generation
    timer = setTimeout(() => {
      search(query, entityType())
        .then((items) => { if (gen === generation) matches.value = items })
        .catch(() => { if (gen === generation) matches.value = [] })
    }, debounceMs)
  })

  const reset = () => {
    generation++
    if (timer !== undefined) clearTimeout(timer)
    matches.value = []
  }

  return { matches, reset }
}
