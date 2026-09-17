import { computed, onMounted, onUnmounted, ref, type Ref } from 'vue'

export interface SidebarResizeOptions {
  initialWidth?: number
  minWidth?: number
  /** Upper bound in pixels; the sidebar is additionally capped at 45% of the grid's width, so a
   * narrow window never leaves the canvas with less room than the panel beside it. */
  maxWidth?: number
}

/** Minimum grid width for dragging to be offered at all — below it the layout has stacked. */
const STACKED_BELOW = 900

/**
 * Drag-to-resize for a two-column layout's right-hand sidebar. `gridRef` is the grid container
 * the width percentage is measured against.
 */
export function useSidebarResize(gridRef: Ref<HTMLElement | null>, options: SidebarResizeOptions = {}) {
  const { initialWidth = 320, minWidth = 260, maxWidth = 520 } = options
  const sidebarWidth = ref(initialWidth)
  const gridStyle = computed(() => ({ '--sidebar-width': `${sidebarWidth.value}px` }))

  const clampSidebarWidth = (nextWidth: number): number => {
    const gridWidth = gridRef.value?.getBoundingClientRect().width ?? window.innerWidth
    const upperBound = Math.min(maxWidth, Math.max(minWidth, Math.floor(gridWidth * 0.45)))
    return Math.min(upperBound, Math.max(minWidth, nextWidth))
  }

  let resizing = false

  const onResizeMove = (e: MouseEvent) => {
    if (!resizing || !gridRef.value) return
    const rect = gridRef.value.getBoundingClientRect()
    sidebarWidth.value = clampSidebarWidth(rect.right - e.clientX)
  }

  const stopResize = () => {
    resizing = false
    document.body.classList.remove('diagram-split-resizing')
    window.removeEventListener('mousemove', onResizeMove)
    window.removeEventListener('mouseup', stopResize)
  }

  const startResize = (e: MouseEvent) => {
    if (!gridRef.value) return
    const rect = gridRef.value.getBoundingClientRect()
    if (rect.width < STACKED_BELOW) return
    e.preventDefault()
    resizing = true
    document.body.classList.add('diagram-split-resizing')
    window.addEventListener('mousemove', onResizeMove)
    window.addEventListener('mouseup', stopResize)
  }

  // The initial width obeys the same bound a drag does. Unclamped, a host that asks for more than
  // 45% of its grid opens that wide, and the first drag snaps the sidebar to the bound with no way
  // back to where it started — the bound is the widest a drag can ever reach.
  onMounted(() => {
    if (gridRef.value && gridRef.value.getBoundingClientRect().width >= STACKED_BELOW) {
      sidebarWidth.value = clampSidebarWidth(sidebarWidth.value)
    }
  })

  onUnmounted(stopResize)

  return { sidebarWidth, gridStyle, startResize }
}
