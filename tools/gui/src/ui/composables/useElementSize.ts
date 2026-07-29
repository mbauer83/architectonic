import { onBeforeUnmount, onMounted, ref, type Ref } from 'vue'

/**
 * Track an element's rendered size for as long as the component lives.
 *
 * Measuring once on mount is the tempting shortcut and it is wrong here: surrounding chrome
 * — a filter summary whose height depends on its text, a legend, a notice row — lays out
 * after the first paint and resizes the element underneath. Anything that later computes
 * geometry from a one-shot measurement is solving for a container that no longer exists.
 *
 * `onResize` fires after the refs are updated, for callers that must recompute something
 * derived from the size rather than merely read it.
 */
export function useElementSize(
  target: () => HTMLElement | null | undefined,
  onResize?: () => void,
): { width: Ref<number>; height: Ref<number> } {
  const width = ref(0)
  const height = ref(0)
  let observer: ResizeObserver | null = null

  const measure = (rect: { width: number; height: number }): void => {
    // A detached or hidden element reports zero; keeping the last real size is more useful
    // than propagating a degenerate one that would make every derived fit collapse.
    if (rect.width <= 0 || rect.height <= 0) return
    width.value = rect.width
    height.value = rect.height
    onResize?.()
  }

  onMounted(() => {
    const element = target()
    if (!element) return
    measure(element.getBoundingClientRect())
    observer = new ResizeObserver((entries) => {
      const entry = entries[0]
      if (entry) measure(entry.contentRect)
    })
    observer.observe(element)
  })

  onBeforeUnmount(() => {
    observer?.disconnect()
    observer = null
  })

  return { width, height }
}
