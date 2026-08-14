<script setup lang="ts">
/**
 * Generic interactive graph canvas: SVG rendering, pan/zoom/drag, node shapes,
 * wrapped labels, multiplicity labels, and zoom controls. Domain-agnostic by
 * contract — it receives normalized nodes/edges plus presentation callbacks
 * and loading/notice state; it never imports architecture, assurance, or
 * viewpoint concepts.
 */
import { onMounted, ref, toRef, watch } from 'vue'
import type { GraphEdge, GraphNode } from '../composables/useForceGraph'
import { useElementSize } from '../composables/useElementSize'
import { useFullscreen } from '../composables/useFullscreen'
import { useGraphPanZoom } from '../composables/useGraphPanZoom'
import { edgeEndRadius, nodeLabelBox } from './graphNodeGeometry'
import {
  contrastTextColor, edgeCardPosFor, edgePathFor, nodeShapePoints, wrapLabel,
  type EdgeEndMarker, type EdgeVisual, type NodeVisual,
} from './GraphCanvas.helpers'
import EdgeMarkerDefs from './EdgeMarkerDefs.vue'
import { edgeMarkerId } from './edgeMarkers'

/** The marker to draw at one end, or nothing. `none` and absent both mean an undecorated end;
 *  the target falls back to the plain arrowhead so a caller that supplies no markers is
 *  unaffected. */
/**
 * The marker to draw at one end.
 *
 * `none` and `undefined` are different answers and must not be conflated. `none` is a caller
 * saying "this end carries no decoration" — an ArchiMate composition has a diamond at its
 * source and deliberately nothing at its target — while `undefined` is a caller that does not
 * speak about markers at all, and keeps the plain arrowhead the canvas has always drawn. The
 * first version returned `undefined` for both, so every explicitly-undecorated end grew an
 * arrowhead back and compositions rendered with a diamond *and* a head.
 */
const markerUrl = (
  marker: EdgeEndMarker | undefined, end: 'source' | 'target',
): string | undefined => {
  if (marker === undefined) return end === 'target' ? 'url(#arrowhead)' : undefined
  return marker === 'none' ? undefined : `url(#${edgeMarkerId(marker, end)})`
}

const props = withDefaults(defineProps<{
  // Readonly: the canvas moves nodes (it writes x/y during a drag) but never adds or removes one.
  // Saying so is what lets a caller hand it a *narrowed* view of the graph rather than the graph.
  nodes: readonly GraphNode[]
  edges: readonly GraphEdge[]
  selectedId: string | null
  selectedEdge: GraphEdge | null
  nodeVisual: (n: GraphNode) => NodeVisual
  edgeVisual: (e: GraphEdge) => EdgeVisual
  isAnchor?: (id: string) => boolean
  showExpandBadge?: (n: GraphNode) => boolean
  clusterEdges?: boolean
  loading?: boolean
  notice?: string | null
}>(), {
  isAnchor: () => false,
  showExpandBadge: () => false,
  clusterEdges: false,
  loading: false,
  notice: null,
})

const emit = defineEmits<{
  nodeClick: [node: GraphNode]
  nodeDblclick: [node: GraphNode]
  edgeClick: [edge: GraphEdge]
  dragTick: []
  resized: [width: number, height: number]
}>()

const svgRef = ref<SVGSVGElement | null>(null)
const svgWidth = ref(800)
const svgHeight = ref(600)

/**
 * The whole viewport goes fullscreen, controls included — the frame rather than the `<svg>`, so the
 * zoom cluster is still reachable once there.
 *
 * Entering or leaving is a framing request: the space changed, and the point of the gesture is to
 * see the graph against the new one, so it re-fits unconditionally rather than honouring a framing
 * chosen for the old size. The fit waits for the *resize* rather than following the toggle,
 * because `fitToView` computes against `svgWidth`/`svgHeight` and those are written by the resize
 * observer below — fitting on the toggle would frame the graph to the size it just left.
 */
const frameRef = ref<HTMLElement | null>(null)
const fullscreen = useFullscreen(frameRef)
let refitOnNextResize = false
watch(fullscreen.isFullscreen, () => { refitOnNextResize = true })

const {
  viewBox, vb, dragging,
  onNodeMouseDown, onSvgMouseDown, onSvgMouseMove, onSvgMouseUp, onWheel,
  zoomBy, fitToView, refitUnlessUserFramed, hasFitted,
} = useGraphPanZoom(svgRef, svgWidth, svgHeight, toRef(props, 'nodes'), () => emit('dragTick'))

// Nodes are laid out in their own coordinate space, so the pre-fit viewBox — the bare
// container rectangle — paints them at whatever scale that implies, usually far too close,
// and the fit a tick later snaps it out. Two paints, the visible one wrong. So: no paint
// until the first fit has landed. Later population changes keep painting and animate into
// their new framing instead; see `hasFitted`.

const frame = useElementSize(() => svgRef.value?.parentElement, () => {
  svgWidth.value = frame.width.value
  svgHeight.value = frame.height.value
  emit('resized', svgWidth.value, svgHeight.value)
  if (refitOnNextResize) { refitOnNextResize = false; fitToView() }
  refitUnlessUserFramed()
})

onMounted(() => {
  viewBox.value = { x: 0, y: 0, w: svgWidth.value, h: svgHeight.value }
})

const centerOn = (x: number, y: number) => {
  viewBox.value.x = x - viewBox.value.w / 2
  viewBox.value.y = y - viewBox.value.h / 2
}

defineExpose({ fitToView, refitUnlessUserFramed, zoomBy, centerOn, dragging })

// Stop the edge at each node's outer boundary so the decoration at that end sits beside it.
// What "outer boundary" means per node is `graphNodeGeometry`'s answer, not one restated here.
const edgePath = (e: GraphEdge) =>
  edgePathFor(props.nodes, e, props.clusterEdges, (id) => edgeEndRadius(props.isAnchor(id)))

// Translucent backing rect for the below-node label — labels can otherwise fall in front of
// edges and become hard to read. The geometry is shared with the cluster layout, which sizes
// its grid cells from it; see `graphNodeGeometry`.
const labelBoxFor = (n: GraphNode) => nodeLabelBox(n.label, n.type, props.isAnchor(n.id))
const edgeCardPos = (e: GraphEdge, frac: number) => edgeCardPosFor(props.nodes, e, frac)
</script>

<template>
  <div
    ref="frameRef"
    class="canvas-frame"
  >
    <div
      v-if="notice"
      class="canvas-notice"
    >
      {{ notice }}
    </div>
    <div
      v-if="loading"
      class="canvas-loading"
    >
      Loading…
    </div>
    <div class="zoom-controls">
      <button
        type="button"
        class="zoom-btn"
        title="Zoom in"
        aria-label="Zoom in"
        @click="zoomBy(0.8)"
      >
        ＋
      </button>
      <button
        type="button"
        class="zoom-btn"
        title="Zoom out"
        aria-label="Zoom out"
        @click="zoomBy(1.25)"
      >
        －
      </button>
      <button
        type="button"
        class="zoom-btn"
        title="Fit all nodes in view"
        aria-label="Fit to view"
        @click="fitToView"
      >
        ⛶
      </button>
      <!-- With the zoom cluster rather than in `DiagramViewportControls`, which pairs fullscreen
           with a Reset that is a *fit*. A graph already has one, always available: its content
           moves when nodes are dragged, so re-framing is wanted even when the viewport itself has
           not been transformed. Mounting that control here would put a second fit on screen. The
           behaviour — Esc, the permissions-policy question, the listener's lifetime — is the
           shared `useFullscreen`, which is the part worth not writing twice. -->
      <button
        v-if="fullscreen.isSupported"
        type="button"
        class="zoom-btn"
        :title="fullscreen.isFullscreen.value ? 'Exit fullscreen (Esc)' : 'View fullscreen'"
        :aria-label="fullscreen.isFullscreen.value ? 'Exit fullscreen' : 'View fullscreen'"
        @click="fullscreen.toggle"
      >
        {{ fullscreen.isFullscreen.value ? '⤡' : '⤢' }}
      </button>
    </div>
    <svg
      ref="svgRef"
      class="graph-svg"
      :style="{ visibility: nodes.length > 0 && !hasFitted ? 'hidden' : 'visible' }"
      :viewBox="vb"
      @mousedown.self="onSvgMouseDown"
      @mousemove="onSvgMouseMove"
      @mouseup="onSvgMouseUp"
      @mouseleave="onSvgMouseUp"
      @wheel.prevent="onWheel"
    >
      <defs>
        <EdgeMarkerDefs />
      </defs>
      <!-- Edges (wider hit area via transparent overlay) -->
      <g
        v-for="(e, i) in edges"
        :key="'e'+i"
        class="graph-edge"
        @click.stop="emit('edgeClick', e)"
      >
        <path
          :d="edgePath(e)"
          :stroke="edgeVisual(e).stroke ?? '#d1d5db'"
          :stroke-width="edgeVisual(e).strokeWidth ?? 1.5"
          :stroke-dasharray="edgeVisual(e).dashArray"
          fill="none"
          :marker-start="markerUrl(edgeVisual(e).sourceMarker, 'source')"
          :marker-end="markerUrl(edgeVisual(e).targetMarker, 'target')"
        />
        <path
          :d="edgePath(e)"
          stroke="transparent"
          stroke-width="10"
          fill="none"
          :class="{ 'edge-selected': selectedEdge === e }"
        />
      </g>
      <!-- Multiplicity labels (rendered above edges, below nodes) -->
      <template
        v-for="(e, i) in edges"
        :key="'card'+i"
      >
        <text
          v-if="e.srcMultiplicity"
          :x="edgeCardPos(e, 0.2).x"
          :y="edgeCardPos(e, 0.2).y"
          text-anchor="middle"
          font-size="8"
          fill="#374151"
          stroke="white"
          stroke-width="3"
          paint-order="stroke"
          pointer-events="none"
        >{{ e.srcMultiplicity }}</text>
        <text
          v-if="e.tgtMultiplicity"
          :x="edgeCardPos(e, 0.8).x"
          :y="edgeCardPos(e, 0.8).y"
          text-anchor="middle"
          font-size="8"
          fill="#374151"
          stroke="white"
          stroke-width="3"
          paint-order="stroke"
          pointer-events="none"
        >{{ e.tgtMultiplicity }}</text>
      </template>
      <!-- Nodes -->
      <g
        v-for="n in nodes"
        :key="n.id"
        class="graph-node"
        :transform="`translate(${n.x}, ${n.y})`"
        @mousedown="onNodeMouseDown($event, n)"
        @click.stop="emit('nodeClick', n)"
        @dblclick.stop="emit('nodeDblclick', n)"
      >
        <!-- Anchor halo: outer ring + the white main-shape stroke = double ring -->
        <polygon
          v-if="isAnchor(n.id)"
          :points="nodeShapePoints(nodeVisual(n).shape, 32)"
          fill="none"
          stroke="#1e293b"
          stroke-width="2"
        />
        <polygon
          :points="nodeShapePoints(nodeVisual(n).shape, isAnchor(n.id) ? 27 : 24)"
          :fill="nodeVisual(n).color"
          :opacity="selectedId === n.id ? 1 : 0.8"
          :stroke="selectedId === n.id ? '#1e293b' : 'white'"
          :stroke-width="selectedId === n.id ? 3 : 2"
        />
        <!-- Glyph inside the node shape; falls back to the type abbreviation when the
             consumer supplies no glyph (e.g. non-ArchiMate graphs). -->
        <svg
          v-if="nodeVisual(n).glyph"
          x="-9"
          y="-9"
          width="18"
          height="18"
          viewBox="0 0 16 16"
          fill="none"
          :stroke="contrastTextColor(nodeVisual(n).color)"
          stroke-width="1.3"
          stroke-linecap="round"
          stroke-linejoin="round"
          pointer-events="none"
        ><g v-html="nodeVisual(n).glyph" /></svg>
        <text
          v-else
          dy="4"
          text-anchor="middle"
          :fill="contrastTextColor(nodeVisual(n).color)"
          font-size="9"
          font-weight="600"
        >
          {{ n.type }}
        </text>
        <!-- Translucent backing so the label stays legible where it crosses edges. -->
        <rect
          v-bind="labelBoxFor(n)"
          rx="3"
          fill="#ffffff"
          opacity="0.6"
          pointer-events="none"
        />
        <!-- Label below the node: bolded type abbreviation, a colon, then the name (wrapped).
             Absolute y (not dy) — dy on <text> does not shift the baseline reliably once a
             child tspan sets its own x, which left the label sitting over the node. -->
        <text
          :y="isAnchor(n.id) ? 46 : 40"
          text-anchor="middle"
          :fill="isAnchor(n.id) ? '#1e293b' : '#374151'"
          font-size="10"
        >
          <title>{{ n.type }}: {{ n.label }}</title>
          <tspan
            v-for="(line, li) in wrapLabel(n.label)"
            :key="li"
            x="0"
            :dy="li === 0 ? 0 : 12"
          ><tspan
            v-if="li === 0"
            font-weight="700"
          >{{ n.type }}: </tspan>{{ line }}</tspan>
        </text>
        <text
          v-if="nodeVisual(n).iconLetter"
          x="-17"
          y="-14"
          text-anchor="middle"
          :fill="contrastTextColor(nodeVisual(n).color)"
          font-size="9"
          font-weight="bold"
          pointer-events="none"
        >{{ nodeVisual(n).iconLetter }}</text>
        <circle
          v-if="showExpandBadge(n)"
          class="expand-badge"
          cx="17"
          cy="-17"
          r="7"
          fill="#2563eb"
          stroke="white"
          stroke-width="1.5"
          cursor="pointer"
        />
        <text
          v-if="showExpandBadge(n)"
          x="17"
          y="-14"
          text-anchor="middle"
          fill="#252327"
          font-size="9"
          font-weight="bold"
          pointer-events="none"
        >+</text>
      </g>
    </svg>
  </div>
</template>

<style scoped>
.canvas-frame { flex: 1; display: flex; flex-direction: column; position: relative; min-height: 0; }
/* A fullscreen element is composited over the browser's own backdrop, which is black; without a
   background of its own the graph would be drawn on it. */
.canvas-frame:fullscreen { background: #fff; }
.canvas-notice {
  position: absolute; top: 10px; left: 50%; transform: translateX(-50%); z-index: 6;
  background: #fef3c7; border: 1px solid #f59e0b; color: #92400e;
  font-size: 12px; padding: 4px 12px; border-radius: 6px; max-width: 80%;
}
.canvas-loading {
  position: absolute; top: 10px; left: 12px; z-index: 6;
  font-size: 12px; color: #6b7280;
}
.zoom-controls {
  position: absolute; right: 12px; bottom: 12px; display: flex; flex-direction: column;
  gap: 4px; z-index: 5;
}
.zoom-btn {
  width: 30px; height: 30px; border: 1px solid #d1d5db; border-radius: 6px; background: white;
  cursor: pointer; font-size: 15px; color: #374151; line-height: 1;
  box-shadow: 0 1px 2px rgba(0,0,0,.08);
}
.zoom-btn:hover { background: #f3f4f6; }
.graph-svg { flex: 1; cursor: grab; user-select: none; }
.graph-svg:active { cursor: grabbing; }
.graph-node { cursor: pointer; }
.graph-node:hover circle:first-child { filter: brightness(1.15); }
.graph-edge { cursor: pointer; }
.graph-edge:hover path:first-child { stroke: #6b7280; }
.edge-selected { stroke: #2563eb !important; opacity: 0.3; }
</style>
