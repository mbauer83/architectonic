import { computed, nextTick, onUnmounted, ref, watch, type Ref } from 'vue'
import { usePanTranslateStyle } from './usePanCanvasStyle'
import { usePanGesture } from './usePanGesture'
import { useWheelZoom } from './useWheelZoom'
import type { ReadingView } from '../../domain/diagramReading'
import type { Extent } from '../../domain/layout/geometry'

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

  const { canvasStyle } = usePanTranslateStyle(tx, ty)

  /**
   * Put the scale on the SVG's own `width`/`height` rather than in the wrapper's transform.
   *
   * An SVG owns its size, and giving it one makes the browser lay the text out at the final size. A
   * scaled wrapper instead rasterises a scaled layer, which is blurry at best — and on a large diagram
   * at a small fit scale it left every element label unpainted until a pointer movement invalidated
   * the layer. The boxes, the diagram title and the grouping headings drew; the labels inside the
   * elements did not, because they are the bulk of the text runs.
   *
   * Both dimensions come from the one scale, so the aspect ratio is unchanged — which matters because
   * PlantUML emits `preserveAspectRatio="none"`, and sizing the two independently would distort.
   */
  const sizeSvgToScale = () => {
    const svgEl = svgContainer.value?.querySelector('svg') as SVGSVGElement | null
    const viewBox = svgEl?.viewBox?.baseVal
    if (!svgEl || !viewBox || viewBox.width <= 0 || viewBox.height <= 0) return
    const width = Math.round(viewBox.width * scale.value)
    const height = Math.round(viewBox.height * scale.value)
    svgEl.setAttribute('width', `${width}px`)
    svgEl.setAttribute('height', `${height}px`)
    // PlantUML also states the size inline, and an inline style beats the attributes.
    svgEl.style.width = `${width}px`
    svgEl.style.height = `${height}px`
  }

  // Every zoom is a resize of the SVG. Watched rather than done at the two call sites, so a future
  // third way of changing the scale cannot forget it.
  watch(scale, sizeSvgToScale)
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

    // The origin keeps a default because the last fallback below does not measure one; the
    // extent never does, because all three paths assign it before it is read.
    let contentX = 0, contentY = 0
    let contentWidth: number, contentHeight: number
    try {
      // The whole drawing, not its first group. PlantUML wraps everything in one root `<g>`, so the
      // two used to agree — but a type that draws its own SVG need not: GSN's first group is a single
      // connector, whose box is a line with no height, so the fit read "nothing to fit" and the
      // diagram opened at its natural size, clipped (B89).
      const bbox = svgEl.getBBox()
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
    // Applied here as well as by the watcher above: a re-render arrives as a *new* SVG element at its
    // natural size, and if the fitted scale happens to be unchanged the watcher never fires.
    sizeSvgToScale()
  }

  const resetView = () => {
    scale.value = fitScale.value
    tx.value = fitTx.value
    ty.value = fitTy.value
  }

  /** Where the picture's own origin sits in the SVG: what a picture point is measured from on screen. */
  const pictureOrigin = (): { x: number; y: number } => {
    const viewBox = (svgContainer.value?.querySelector('svg') as SVGSVGElement | null)?.viewBox?.baseVal
    return { x: viewBox?.x ?? 0, y: viewBox?.y ?? 0 }
  }

  /** The window as a reading names it: the picture point at its centre, and the zoom in percent. */
  const windowView = (): ReadingView | null => {
    const rect = containerRef.value?.getBoundingClientRect()
    if (!rect || rect.width <= 0) return null
    const origin = pictureOrigin()
    return {
      x: origin.x + (rect.width / 2 - tx.value) / scale.value,
      y: origin.y + (rect.height / 2 - ty.value) / scale.value,
      percent: scale.value * 100,
    }
  }

  /** Show the window a reading names: its centre point in the middle, at its zoom. */
  const showView = (view: ReadingView) => {
    const rect = containerRef.value?.getBoundingClientRect()
    if (!rect || rect.width <= 0 || view.percent <= 0) return
    const origin = pictureOrigin()
    scale.value = view.percent / 100
    tx.value = rect.width / 2 - (view.x - origin.x) * scale.value
    ty.value = rect.height / 2 - (view.y - origin.y) * scale.value
  }

  /** Fit the window to a part of the picture, never closer than its natural size. */
  const frame = (extent: Extent, padding = 40) => {
    const rect = containerRef.value?.getBoundingClientRect()
    const width = extent.right - extent.left
    const height = extent.bottom - extent.top
    if (!rect || width <= 0 || height <= 0) return
    const fitted = Math.min((rect.width - padding * 2) / width, (rect.height - padding * 2) / height, 1)
    showView({ x: extent.left + width / 2, y: extent.top + height / 2, percent: Math.max(fitted, 0.05) * 100 })
  }

  /** Move the window by the least that brings a part of the picture *margin* pixels inside it. */
  const reveal = (extent: Extent, margin = 32) => {
    const rect = containerRef.value?.getBoundingClientRect()
    if (!rect) return
    const origin = pictureOrigin()
    const shift = (low: number, high: number, size: number): number =>
      (low < margin ? margin - low : high > size - margin ? Math.max(size - margin - high, margin - low) : 0)
    const left = tx.value + (extent.left - origin.x) * scale.value
    const top = ty.value + (extent.top - origin.y) * scale.value
    tx.value += shift(left, left + (extent.right - extent.left) * scale.value, rect.width)
    ty.value += shift(top, top + (extent.bottom - extent.top) * scale.value, rect.height)
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

  return {
    scale, tx, ty, canvasStyle, isTransformed, onMouseDown, resetView, fitDiagramToViewport,
    windowView, showView, frame, reveal,
  }
}
