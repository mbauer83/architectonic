import { Effect, Exit } from 'effect'
import { ref } from 'vue'
import type { PromotionArtifact } from './promotionShared'

export const usePromotionSearch = (
  searchFn: (query: string) => Effect.Effect<PromotionArtifact[], unknown>,
) => {
  const query = ref('')
  const results = ref<PromotionArtifact[]>([])
  const showDropdown = ref(false)
  const errorMessage = ref<string | null>(null)
  let timer: ReturnType<typeof setTimeout> | null = null

  const runSearch = async () => {
    const exit = await Effect.runPromiseExit(searchFn(query.value))
    Exit.match(exit, {
      onSuccess: (nextResults) => {
        results.value = nextResults
        showDropdown.value = Boolean(query.value.trim() && nextResults.length)
        errorMessage.value = null
      },
      onFailure: (error) => {
        results.value = []
        showDropdown.value = false
        errorMessage.value = String(error)
      },
    })
  }

  const scheduleSearch = () => {
    if (timer) clearTimeout(timer)
    if (!query.value.trim()) {
      results.value = []
      showDropdown.value = false
      errorMessage.value = null
      return
    }
    timer = setTimeout(() => {
      void runSearch()
    }, 220)
  }

  const closeDropdown = () => {
    setTimeout(() => { showDropdown.value = false }, 150)
  }

  const clear = () => {
    query.value = ''
    results.value = []
    showDropdown.value = false
  }

  const cleanup = () => {
    if (timer) clearTimeout(timer)
  }

  return { query, results, showDropdown, errorMessage, scheduleSearch, closeDropdown, clear, cleanup }
}
