/**
 * Pan, zoom, hover-tooltip placement and press-to-select for a treemap canvas.
 *
 * Extracted from `Treemap` so the component is a drawing and this is the gesture handling. Both are
 * vocabulary-free: this knows about pixels, a host element and an opaque leaf key, and nothing about
 * what a leaf is.
 *
 * The press-to-select rule is the reason this is not just a pan-zoom helper: the canvas has to be
 * both draggable and clickable without a modifier key, so a press that does not travel counts as a
 * click on the tile it started on.
 */
import { computed, onBeforeUnmount, onMounted, ref, type Ref } from 'vue'
import { clampZoom, movedFar } from '../components/Treemap.helpers'

type Point = { x: number; y: number }

const TOOLTIP_WIDTH = 260
const TOOLTIP_HEIGHT = 120
const TOOLTIP_GAP = 12
const TOOLTIP_DELAY_MS = 250

const bounded = (value: number, min: number, max: number) =>
  Math.max(min, Math.min(max, value))

export function useTreemapInteraction<TLeaf>(
  hostRef: Ref<HTMLElement | null>,
  svgRef: Ref<SVGSVGElement | null>,
  onSelect: (key: string) => void,
) {
  const size = ref({ width: 960, height: 620 })
  const zoom = ref(1)
  const pan = ref<Point>({ x: 0, y: 0 })
  const panning = ref(false)
  const dragStart = ref<Point>({ x: 0, y: 0 })
  const panOrigin = ref<Point>({ x: 0, y: 0 })
  const movedDuringGesture = ref(false)
  const pressedLeafId = ref<string | null>(null)
  const tooltipLeaf = ref<TLeaf | null>(null)
  const tooltipPos = ref<Point>({ x: 0, y: 0 })
  let observer: ResizeObserver | null = null
  let hoverTimer: ReturnType<typeof setTimeout> | null = null

  const viewBox = computed(() => `0 0 ${size.value.width} ${size.value.height}`)
  const transform = computed(
    () => `translate(${pan.value.x}, ${pan.value.y}) scale(${zoom.value})`,
  )

  const resetView = () => { zoom.value = 1; pan.value = { x: 0, y: 0 } }

  const clearTooltip = () => {
    if (hoverTimer) clearTimeout(hoverTimer)
    hoverTimer = null
    tooltipLeaf.value = null
  }

  const updateSize = () => {
    const rect = hostRef.value?.getBoundingClientRect()
    if (!rect) return
    size.value = { width: rect.width, height: Math.max(rect.height, 540) }
  }

  /** Placed on whichever side has room, and never off the host — a tooltip that has to be chased
   *  off-screen is a tooltip nobody reads. */
  const queueTooltip = (leaf: TLeaf, clientX: number, clientY: number) => {
    clearTooltip()
    const rect = hostRef.value?.getBoundingClientRect()
    if (!rect || panning.value) return
    const localX = clientX - rect.left
    const localY = clientY - rect.top
    const roomRight = rect.width - localX
    const roomBottom = rect.height - localY
    tooltipPos.value = {
      x: bounded(
        roomRight > TOOLTIP_WIDTH + TOOLTIP_GAP
          ? localX + TOOLTIP_GAP
          : localX - TOOLTIP_WIDTH - TOOLTIP_GAP,
        8, Math.max(8, rect.width - TOOLTIP_WIDTH - 8),
      ),
      y: bounded(
        roomBottom > TOOLTIP_HEIGHT + TOOLTIP_GAP
          ? localY + TOOLTIP_GAP
          : localY - TOOLTIP_HEIGHT - TOOLTIP_GAP,
        8, Math.max(8, rect.height - TOOLTIP_HEIGHT - 8),
      ),
    }
    hoverTimer = setTimeout(() => {
      tooltipLeaf.value = leaf
      hoverTimer = null
    }, TOOLTIP_DELAY_MS)
  }

  /** Zoom about the cursor, so the thing under the pointer stays under it. */
  const zoomAround = (clientX: number, clientY: number, nextZoom: number) => {
    const svgRect = svgRef.value?.getBoundingClientRect()
    if (!svgRect) return
    const targetZoom = clampZoom(nextZoom)
    const px = clientX - svgRect.left
    const py = clientY - svgRect.top
    const wx = (px - pan.value.x) / zoom.value
    const wy = (py - pan.value.y) / zoom.value
    zoom.value = targetZoom
    pan.value = { x: px - wx * targetZoom, y: py - wy * targetZoom }
  }

  const zoomByButton = (delta: number) => {
    const rect = svgRef.value?.getBoundingClientRect()
    if (!rect) return
    zoomAround(rect.left + rect.width / 2, rect.top + rect.height / 2, zoom.value + delta)
  }

  const onWheel = (event: WheelEvent) => {
    event.preventDefault()
    clearTooltip()
    zoomAround(event.clientX, event.clientY, zoom.value * (event.deltaY > 0 ? 0.9 : 1.12))
  }

  const startPan = (event: MouseEvent) => {
    if (event.button !== 0) return
    clearTooltip()
    panning.value = true
    dragStart.value = { x: event.clientX, y: event.clientY }
    panOrigin.value = { ...pan.value }
    movedDuringGesture.value = false
    const leaf = (event.target as Element | null)?.closest<SVGElement>('[data-leaf-id]')
    pressedLeafId.value = leaf?.dataset.leafId ?? null
  }

  const onMove = (event: MouseEvent) => {
    if (!panning.value) return
    if (movedFar(dragStart.value, { x: event.clientX, y: event.clientY })) {
      movedDuringGesture.value = true
    }
    clearTooltip()
    pan.value = {
      x: panOrigin.value.x + event.clientX - dragStart.value.x,
      y: panOrigin.value.y + event.clientY - dragStart.value.y,
    }
  }

  const stopPan = () => {
    if (panning.value && pressedLeafId.value && !movedDuringGesture.value) {
      onSelect(pressedLeafId.value)
    }
    panning.value = false
    movedDuringGesture.value = false
    pressedLeafId.value = null
  }

  onMounted(() => {
    updateSize()
    observer = new ResizeObserver(updateSize)
    if (hostRef.value) observer.observe(hostRef.value)
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', stopPan)
  })

  onBeforeUnmount(() => {
    clearTooltip()
    observer?.disconnect()
    window.removeEventListener('mousemove', onMove)
    window.removeEventListener('mouseup', stopPan)
  })

  return {
    size, zoom, viewBox, transform,
    tooltipLeaf, tooltipPos,
    resetView, clearTooltip, queueTooltip, zoomByButton, onWheel, startPan,
  }
}
