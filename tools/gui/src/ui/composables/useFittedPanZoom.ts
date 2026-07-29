import { computed, nextTick, onUnmounted, ref, watch, type Ref } from 'vue'

/**
 * Pan/zoom/fit-to-viewport for a rendered SVG inside `containerRef`, with `svgContainer`
 * pointing at the wrapper the SVG itself is mounted into (so `fitDiagramToViewport` can
 * measure its content bbox/viewBox). Wheel-to-zoom (cursor-anchored), drag-to-pan, and a
 * ResizeObserver that keeps re-fitting until the user has manually transformed the view.
 *
 * Distinct from the simpler `usePanZoom` (fixed scale=1/translate=0 reset, no viewport
 * measurement) `PreviewViewport.vue` already uses — that composable's callers don't need
 * fit-to-content, so this stays a separate, purpose-built composable rather than growing
 * that one a second, more complex mode.
 */
export function useFittedPanZoom(containerRef: Ref<HTMLElement | null>, svgContainer: Ref<HTMLElement | null>) {
  const scale = ref(1)
  const tx = ref(0)
  const ty = ref(0)
  const fitScale = ref(1)
  const fitTx = ref(0)
  const fitTy = ref(0)
  let resizeObserver: ResizeObserver | null = null
  let dragging = false
  let drag = { x: 0, y: 0, tx: 0, ty: 0 }

  const canvasStyle = computed(() => ({
    transform: `translate(${tx.value}px, ${ty.value}px) scale(${scale.value})`,
    transformOrigin: '0 0',
    willChange: 'transform',
    display: 'inline-block',
  }))
  const isTransformed = computed(() =>
    Math.abs(scale.value - fitScale.value) > 0.001
    || Math.abs(tx.value - fitTx.value) > 0.5
    || Math.abs(ty.value - fitTy.value) > 0.5,
  )

  const fitDiagramToViewport = async () => {
    await nextTick()
    const container = containerRef.value
    const svgEl = svgContainer.value?.querySelector('svg') as SVGSVGElement | null
    if (!container || !svgEl) return

    let contentWidth = 0, contentHeight = 0, contentX = 0, contentY = 0
    try {
      const graphRoot = svgEl.querySelector('g')
      const bbox = (graphRoot ?? svgEl).getBBox()
      contentX = bbox.x; contentY = bbox.y
      contentWidth = bbox.width; contentHeight = bbox.height
    } catch {
      const viewBox = svgEl.viewBox?.baseVal
      if (viewBox && viewBox.width > 0 && viewBox.height > 0) {
        contentX = viewBox.x; contentY = viewBox.y
        contentWidth = viewBox.width; contentHeight = viewBox.height
      } else {
        const widthAttr = Number(svgEl.getAttribute('width') ?? '')
        const heightAttr = Number(svgEl.getAttribute('height') ?? '')
        contentWidth = Number.isFinite(widthAttr) && widthAttr > 0 ? widthAttr : svgEl.clientWidth
        contentHeight = Number.isFinite(heightAttr) && heightAttr > 0 ? heightAttr : svgEl.clientHeight
      }
    }
    if (!contentWidth || !contentHeight) return

    const rect = container.getBoundingClientRect()
    const horizontalPadding = 24
    const topPadding = Math.min(Math.max(rect.height * 0.035, 16), 40)
    const bottomPadding = 24
    const availableWidth = Math.max(rect.width - horizontalPadding * 2, 80)
    const availableHeight = Math.max(rect.height - topPadding - bottomPadding, 80)
    // Contain-fit when the whole diagram stays legible; otherwise fit to WIDTH at up to
    // natural size and let the rest scroll — a wide diagram squeezed into the viewport
    // renders as an illegible strip, which is worse than panning.
    const LEGIBLE_MIN_SCALE = 0.5
    const containScale = Math.min(availableWidth / contentWidth, availableHeight / contentHeight)
    const fittedScale = containScale >= LEGIBLE_MIN_SCALE
      ? containScale
      : Math.min(availableWidth / contentWidth, 1)
    if (!Number.isFinite(fittedScale) || fittedScale <= 0) return

    fitScale.value = fittedScale
    fitTx.value = (rect.width - contentWidth * fittedScale) / 2 - contentX * fittedScale
    fitTy.value = topPadding - contentY * fittedScale
    scale.value = fitScale.value
    tx.value = fitTx.value
    ty.value = fitTy.value
  }

  const onWheel = (e: WheelEvent) => {
    e.preventDefault()
    const factor = e.deltaY < 0 ? 1.15 : 1 / 1.15
    const ns = Math.min(8, Math.max(0.2, scale.value * factor))
    const r = ns / scale.value
    const rect = containerRef.value!.getBoundingClientRect()
    tx.value = (e.clientX - rect.left) * (1 - r) + tx.value * r
    ty.value = (e.clientY - rect.top) * (1 - r) + ty.value * r
    scale.value = ns
  }

  const onMouseMove = (e: MouseEvent) => {
    if (!dragging) return
    tx.value = drag.tx + (e.clientX - drag.x)
    ty.value = drag.ty + (e.clientY - drag.y)
  }
  const onMouseUp = () => {
    dragging = false
    window.removeEventListener('mousemove', onMouseMove)
    window.removeEventListener('mouseup', onMouseUp)
  }
  const onMouseDown = (e: MouseEvent) => {
    if ((e.target as HTMLElement).closest('[data-entity-id], [data-conn-id], button, a')) return
    dragging = true
    drag = { x: e.clientX, y: e.clientY, tx: tx.value, ty: ty.value }
    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
  }
  const resetView = () => {
    scale.value = fitScale.value
    tx.value = fitTx.value
    ty.value = fitTy.value
  }

  watch(containerRef, (el, prev) => {
    prev?.removeEventListener('wheel', onWheel)
    el?.addEventListener('wheel', onWheel, { passive: false })
    resizeObserver?.disconnect()
    resizeObserver = null
    if (!el) return
    resizeObserver = new ResizeObserver(() => {
      if (!isTransformed.value) void fitDiagramToViewport()
    })
    resizeObserver.observe(el)
  })

  onUnmounted(() => {
    resizeObserver?.disconnect()
    containerRef.value?.removeEventListener('wheel', onWheel)
    window.removeEventListener('mousemove', onMouseMove)
    window.removeEventListener('mouseup', onMouseUp)
  })

  return { scale, tx, ty, canvasStyle, isTransformed, onMouseDown, resetView, fitDiagramToViewport }
}
