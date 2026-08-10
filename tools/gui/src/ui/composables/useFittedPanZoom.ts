import { computed, nextTick, onUnmounted, ref, watch, type Ref } from 'vue'
import { usePanGesture } from './usePanGesture'
import { useWheelZoom } from './useWheelZoom'

/**
 * Fit-to-viewport framing for a rendered SVG inside `containerRef`, with `svgContainer` pointing at
 * the wrapper the SVG itself is mounted into (so `fitDiagramToViewport` can measure its content
 * bbox/viewBox), plus a ResizeObserver that keeps re-fitting until the reader has moved the view
 * themselves. The two gestures — `usePanGesture`, `useWheelZoom` — are shared with `usePanZoom`.
 *
 * What remains distinct from that simpler composable is only the framing: it resets to
 * scale=1/translate=0 and measures nothing, which is all `PreviewViewport.vue` needs. Keeping the
 * two apart is what stops fit-to-content becoming a second mode of one composable, switched by a
 * flag — the gestures they genuinely share now live in one place instead.
 */
export function useFittedPanZoom(containerRef: Ref<HTMLElement | null>, svgContainer: Ref<HTMLElement | null>) {
  const scale = ref(1)
  const tx = ref(0)
  const ty = ref(0)
  const fitScale = ref(1)
  const fitTx = ref(0)
  const fitTy = ref(0)
  let resizeObserver: ResizeObserver | null = null
  const { onMouseDown } = usePanGesture(tx, ty)
  useWheelZoom(containerRef, { scale, tx, ty })

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

  const resetView = () => {
    scale.value = fitScale.value
    tx.value = fitTx.value
    ty.value = fitTy.value
  }

  watch(containerRef, (el) => {
    resizeObserver?.disconnect()
    resizeObserver = null
    if (!el) return
    resizeObserver = new ResizeObserver(() => {
      if (!isTransformed.value) void fitDiagramToViewport()
    })
    resizeObserver.observe(el)
  })

  onUnmounted(() => resizeObserver?.disconnect())

  return { scale, tx, ty, canvasStyle, isTransformed, onMouseDown, resetView, fitDiagramToViewport }
}
