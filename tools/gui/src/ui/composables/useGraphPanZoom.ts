import { computed, ref, type Ref } from 'vue'
import type { GraphNode } from './useForceGraph'
import { fitViewBox, type ViewBoxRect } from '../components/GraphCanvas.helpers'

/**
 * SVG pan/zoom/drag interaction for the graph explorer: wheel zoom around the cursor,
 * background panning, node dragging (pins the node while held), plus the explicit
 * zoom-in/out and fit-to-view controls — one place for all viewBox mutations.
 */
export function useGraphPanZoom(
  svgRef: Ref<SVGSVGElement | null>,
  svgWidth: Ref<number>,
  svgHeight: Ref<number>,
  // Read only here — it frames the nodes and never changes which ones there are.
  nodes: Ref<readonly GraphNode[]>,
  onDragTick: () => void,
) {
  const viewBox = ref<ViewBoxRect>({ x: 0, y: 0, w: 800, h: 600 })
  const isPanning = ref(false)
  const panStart = ref({ x: 0, y: 0 })
  const dragging = ref<GraphNode | null>(null)
  const dragOffset = ref({ x: 0, y: 0 })

  /**
   * Pointer travel, in screen pixels, before a press on a node becomes a drag.
   *
   * Without it every press was a drag: the node was pinned, nudged by whatever pixel or two
   * the hand moved between press and release, and a `dragTick` fired on release. The visible
   * consequence was that expanding a node took two attempts — the first double-click was
   * spent dragging it a couple of pixels, and the layout that ran on release moved the graph
   * out from under the pointer before the second click landed.
   */
  const DRAG_THRESHOLD_PX = 4

  //: Set on mousedown over a node; promoted to `dragging` only once the pointer has moved.
  const pressed = ref<{ node: GraphNode; clientX: number; clientY: number } | null>(null)

  const toSvgCoords = (clientX: number, clientY: number) => {
    const svg = svgRef.value
    if (!svg) return { x: clientX, y: clientY }
    const pt = svg.createSVGPoint()
    pt.x = clientX
    pt.y = clientY
    const ctm = svg.getScreenCTM()?.inverse()
    if (!ctm) return { x: clientX, y: clientY }
    const svgPt = pt.matrixTransform(ctm)
    return { x: svgPt.x, y: svgPt.y }
  }

  const onNodeMouseDown = (e: MouseEvent, n: GraphNode) => {
    e.preventDefault()
    e.stopPropagation()
    pressed.value = { node: n, clientX: e.clientX, clientY: e.clientY }
  }

  /** Promote a held press to a real drag once the pointer has travelled far enough. */
  const beginDragIfMoved = (e: MouseEvent): boolean => {
    const held = pressed.value
    if (held === null) return false
    const travelled = Math.hypot(e.clientX - held.clientX, e.clientY - held.clientY)
    if (travelled < DRAG_THRESHOLD_PX) return false
    pressed.value = null
    dragging.value = held.node
    held.node.pinned = true
    // Anchored on where the press started, not where the pointer is now, so the node does not
    // jump by the threshold distance at the moment the drag begins.
    const svgPt = toSvgCoords(held.clientX, held.clientY)
    dragOffset.value = { x: held.node.x - svgPt.x, y: held.node.y - svgPt.y }
    return true
  }

  const onSvgMouseMove = (e: MouseEvent) => {
    beginDragIfMoved(e)
    if (dragging.value) {
      const svgPt = toSvgCoords(e.clientX, e.clientY)
      dragging.value.x = svgPt.x + dragOffset.value.x
      dragging.value.y = svgPt.y + dragOffset.value.y
      onDragTick()
      return
    }
    if (isPanning.value) {
      const dx = (e.clientX - panStart.value.x) * (viewBox.value.w / svgWidth.value)
      const dy = (e.clientY - panStart.value.y) * (viewBox.value.h / svgHeight.value)
      viewBox.value.x -= dx
      viewBox.value.y -= dy
      panStart.value = { x: e.clientX, y: e.clientY }
    }
  }

  const onSvgMouseUp = () => {
    // A press that never became a drag is a click: nothing was pinned, nothing moved, and
    // firing a layout tick here is what used to shift the graph between the two halves of a
    // double-click.
    pressed.value = null
    if (dragging.value) {
      dragging.value.pinned = false
      dragging.value = null
      onDragTick()
    }
    isPanning.value = false
  }

  const onSvgMouseDown = (e: MouseEvent) => {
    isPanning.value = true
    panStart.value = { x: e.clientX, y: e.clientY }
  }

  const onWheel = (e: WheelEvent) => {
    e.preventDefault()
    const factor = e.deltaY > 0 ? 1.1 : 0.9
    const svgPt = toSvgCoords(e.clientX, e.clientY)
    const box = viewBox.value
    box.x = svgPt.x - (svgPt.x - box.x) * factor
    box.y = svgPt.y - (svgPt.y - box.y) * factor
    box.w *= factor
    box.h *= factor
  }

  const zoomBy = (factor: number) => {
    const box = viewBox.value
    const cx = box.x + box.w / 2
    const cy = box.y + box.h / 2
    box.w *= factor
    box.h *= factor
    box.x = cx - box.w / 2
    box.y = cy - box.h / 2
  }

  //: The viewBox the last programmatic fit produced. Anything else means the user has
  //: panned, zoomed or dragged since, and their framing is theirs to keep.

  /**
   * Whether a fit has *ever* landed on a non-empty population — the canvas paints from then on.
   *
   * Deliberately never cleared again. It used to be invalidated on every population change, so
   * that each new set of nodes waited for its own fit; but expansion grows the population, and
   * hiding the canvas until the graph had rearranged itself is what made an expansion read as
   * the graph vanishing and reappearing already expanded. The zoom-flip this gate was written
   * for is an *initial-load* defect — the first nodes painting into a frame measured without
   * them — and waiting for the first fit is the whole of the fix for it.
   */
  const hasFitted = ref(false)

  //: The framing the last fit produced. Distinct from "the fit for what is on screen now", and the
  //: distinction is the whole of why both exist — see `isTransformed` and `isUserFramed` below.
  let lastFitted: ViewBoxRect | null = null

  const fitToView = () => {
    viewBox.value = fitViewBox(nodes.value, svgWidth.value, svgHeight.value)
    lastFitted = { ...viewBox.value }
    // An empty population has no framing, so fitting it must not claim one. It used to: the
    // container's own resize fires before any node arrives, that fit was recorded, and the
    // first nodes then painted into a frame computed without them — visible, and wrong.
    if (nodes.value.length > 0) hasFitted.value = true
  }

  /**
   * Whether the reader has taken the framing over: it has moved since the last fit was *performed*.
   *
   * Not the same question as `isTransformed`, and the two must not be merged — they were, and it
   * cost the animated layouts their framing. While a cluster tween or a force run is in motion the
   * content moves under a still viewport, so "the framing no longer fits the content" is true on
   * every frame and an auto-refit keyed on it never fires: the graph animates into an arrangement
   * the viewport was never re-framed for. Panning is what this asks about, and panning moves the
   * viewport rather than the content.
   */
  const isUserFramed = (): boolean => {
    if (lastFitted === null) return false
    const box = viewBox.value
    return Math.abs(box.x - lastFitted.x) > 0.5 || Math.abs(box.y - lastFitted.y) > 0.5
      || Math.abs(box.w - lastFitted.w) > 0.5 || Math.abs(box.h - lastFitted.h) > 0.5
  }

  /**
   * Whether a reset would do anything: the framing on screen is not the one fitting the graph.
   *
   * The same question `useFittedPanZoom.isTransformed` answers for a rendered diagram, and stated
   * the same way — against the *fit for the current content*, not against the last fit performed.
   * On a graph that distinction carries weight a diagram never puts on it: dragging a node moves
   * the content without touching the viewport, so a framing that was a fit a moment ago is not one
   * now. Asked this way, the control appears exactly when it has something to do.
   */
  const isTransformed = computed(() => {
    if (!hasFitted.value) return false
    const fit = fitViewBox(nodes.value, svgWidth.value, svgHeight.value)
    const box = viewBox.value
    return Math.abs(box.x - fit.x) > 0.5 || Math.abs(box.y - fit.y) > 0.5
      || Math.abs(box.w - fit.w) > 0.5 || Math.abs(box.h - fit.h) > 0.5
  })

  /**
   * Re-fit after a container resize, unless the user has framed the view themselves.
   *
   * A fit is only correct for the container it was computed against, and the container
   * keeps changing after the first one: the surrounding filter summary, legend and notice
   * rows lay out once the result arrives. Without this, initialisation reliably fits to an
   * intermediate size and leaves the graph mis-scaled — the same failure as never fitting.
   * Asks `isUserFramed` rather than `isTransformed`: a resize should not take away a framing the
   * *reader* chose, but it must still re-fit a graph whose own content has moved, which is every
   * frame of an animated layout.
   */
  const refitUnlessUserFramed = () => {
    if (!isUserFramed()) fitToView()
  }

  const vb = computed(() => `${viewBox.value.x} ${viewBox.value.y} ${viewBox.value.w} ${viewBox.value.h}`)

  return {
    viewBox, vb, dragging,
    onNodeMouseDown, onSvgMouseDown, onSvgMouseMove, onSvgMouseUp, onWheel,
    zoomBy, fitToView, refitUnlessUserFramed, hasFitted, isTransformed,
  }
}
