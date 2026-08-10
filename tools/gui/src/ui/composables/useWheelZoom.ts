import { onUnmounted, watch, type Ref } from 'vue'

/** How far one wheel notch moves the scale, and the range it may not leave. */
const ZOOM_STEP = 1.15
const MIN_SCALE = 0.2
const MAX_SCALE = 8

/** The three numbers a pan/zoom viewport is made of, as the composable that owns them holds them. */
export interface ViewTransform {
  scale: Ref<number>
  tx: Ref<number>
  ty: Ref<number>
}

/**
 * Cursor-anchored wheel zoom over a viewport.
 *
 * Anchored means the point under the cursor stays under the cursor: the translation is corrected by
 * the same ratio the scale moved by, so zooming reads as approaching the thing being pointed at
 * rather than as the picture sliding away from it.
 *
 * Non-passive, because the page must not scroll while the diagram zooms.
 */
export function useWheelZoom(
  containerRef: Readonly<Ref<HTMLElement | null>>,
  { scale, tx, ty }: ViewTransform,
): void {
  const onWheel = (event: WheelEvent) => {
    event.preventDefault()
    const container = containerRef.value
    if (container === null) return
    const next = Math.min(MAX_SCALE, Math.max(MIN_SCALE, scale.value * (event.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP)))
    const ratio = next / scale.value
    const rect = container.getBoundingClientRect()
    tx.value = (event.clientX - rect.left) * (1 - ratio) + tx.value * ratio
    ty.value = (event.clientY - rect.top) * (1 - ratio) + ty.value * ratio
    scale.value = next
  }

  // `immediate`, because the element is not always a template ref that arrives after setup — given
  // one already resolved, a watcher that only fires on change would never attach at all.
  watch(containerRef, (element, previous) => {
    previous?.removeEventListener('wheel', onWheel)
    element?.addEventListener('wheel', onWheel, { passive: false })
  }, { immediate: true })
  onUnmounted(() => containerRef.value?.removeEventListener('wheel', onWheel))
}
