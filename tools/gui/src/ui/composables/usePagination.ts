import { computed, ref } from 'vue'
import type { ComputedRef } from 'vue'

export function usePagination(total: ComputedRef<number>, pageSize: number) {
  const currentPage = ref(0)
  const pageCount = computed(() => Math.max(1, Math.ceil(total.value / pageSize)))
  const hasPrev = computed(() => currentPage.value > 0)
  const hasNext = computed(() => currentPage.value < pageCount.value - 1)
  const goNext = () => { if (hasNext.value) currentPage.value++ }
  const goPrev = () => { if (hasPrev.value) currentPage.value-- }
  const reset = () => { currentPage.value = 0 }
  const offset = computed(() => currentPage.value * pageSize)
  return { currentPage, pageCount, hasPrev, hasNext, goNext, goPrev, reset, offset }
}
