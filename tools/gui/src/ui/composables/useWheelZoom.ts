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
 *
 * **A wheel over something that scrolls belongs to that thing.** The listener is on the viewport, and
 * in fullscreen the companion sidebar is teleported *inside* it — so a reader scrolling a list of
 * twenty entities was zooming the diagram instead, with the list refusing to move. The rule is stated
 * as a property of the element under the pointer rather than as a list of components to exclude: any
 * scrollable ancestor between the target and the viewport keeps its own wheel, and a future panel
 * docked the same way needs no change here.
 */
export function useWheelZoom(
  containerRef: Readonly<Ref<HTMLElement | null>>,
  { scale, tx, ty }: ViewTransform,
): void {
  /** The nearest thing between *target* and the viewport that scrolls, if any. */
  const scrollableUnderPointer = (target: EventTarget | null, container: HTMLElement): boolean => {
    let element = target instanceof Element ? target : null
    while (element !== null && element !== container) {
      const overflow = window.getComputedStyle(element).overflowY
      // Both halves matter: an `auto` container with nothing to scroll is not scrolling, and letting
      // it swallow the wheel would make the diagram unzoomable wherever such a panel sits.
      if ((overflow === 'auto' || overflow === 'scroll') && element.scrollHeight > element.clientHeight) {
        return true
      }
      element = element.parentElement
    }
    return false
  }

  const onWheel = (event: WheelEvent) => {
    const container = containerRef.value
    if (container === null) return
    // Returned *without* `preventDefault`, so the scrollable element receives the wheel it was given.
    if (scrollableUnderPointer(event.target, container)) return
    event.preventDefault()
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
