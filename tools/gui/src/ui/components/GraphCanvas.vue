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
import { edgeEndRadius } from './graphNodeGeometry'
import {
  edgeCardPosFor, edgePathFor,
  type EdgeEndMarker, type EdgeVisual, type NodeVisual,
} from './GraphCanvas.helpers'
import DiagramViewportControls from './DiagramViewportControls.vue'
import EdgeMarkerDefs from './EdgeMarkerDefs.vue'
import GraphCanvasNode from './GraphCanvasNode.vue'
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
  backgroundClick: []
}>()

const svgRef = ref<SVGSVGElement | null>(null)
const svgWidth = ref(800)
const svgHeight = ref(600)

/**
 * The whole viewport goes fullscreen, controls included — the frame rather than the `<svg>`, so the
 * zoom cluster is still reachable once there.
 *
 * Entering or leaving is a framing request — the same one the diagram viewport makes on the same
 * gesture: the space changed, and the point of the gesture is to see the picture against the new
 * one, so it re-fits unconditionally rather than honouring a framing chosen for the old size.
 *
 * It differs from the diagram's only in *when*, and only because it has to. A diagram's fit awaits
 * `nextTick` and then measures the container; this one computes against `svgWidth`/`svgHeight`,
 * which a resize observer writes — so a fit that followed the toggle would frame the graph to the
 * size it just left. It waits for the resize instead, and arrives at the same place.
 */
const frameRef = ref<HTMLElement | null>(null)
const fullscreen = useFullscreen(frameRef)
let refitOnNextResize = false
watch(fullscreen.isFullscreen, () => { refitOnNextResize = true })

const {
  viewBox, vb, dragging,
  onNodeMouseDown, onSvgMouseDown, onSvgMouseMove, onSvgMouseUp, onWheel,
  zoomBy, fitToView, refitUnlessUserFramed, hasFitted, isTransformed, wasPan,
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

defineExpose({
  /** The element the browser makes fullscreen, and so the host a docked sidebar teleports into. */
  frameEl: frameRef,
  /** The live drawing and the frame it is being read through — what a snapshot is *of*. */
  svgEl: svgRef,
  frame: viewBox,
  isFullscreen: fullscreen.isFullscreen,
  fitToView, refitUnlessUserFramed, zoomBy, centerOn, dragging,
})

/**
 * A click on blank space deselects, as it does on a diagram.
 *
 * `.self`, so only the background is meant — nodes and edges stop their own clicks. Guarded on
 * whether the gesture travelled: releasing a pan produces a click too, and deselecting at the end
 * of every drag would make the panel impossible to keep open while moving around the graph.
 */
const onBackgroundClick = () => { if (!wasPan()) emit('backgroundClick') }

// Stop the edge at each node's outer boundary so the decoration at that end sits beside it.
// What "outer boundary" means per node is `graphNodeGeometry`'s answer, not one restated here.
const edgePath = (e: GraphEdge) =>
  edgePathFor(props.nodes, e, props.clusterEdges, (id) => edgeEndRadius(props.isAnchor(id)))

// Translucent backing rect for the below-node label — labels can otherwise fall in front of
// edges and become hard to read. The geometry is shared with the cluster layout, which sizes
// its grid cells from it; see `graphNodeGeometry`.
const edgeCardPos = (e: GraphEdge, frac: number) => edgeCardPosFor(props.nodes, e, frac)
</script>

<template>
  <div
    ref="frameRef"
    class="canvas-frame viewport-host"
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
    </div>
    <!-- The same chrome a rendered diagram's viewport carries, in the same corner, with the same
         labels and the same hint line. Reset is the fit: a separate ⛶ beside it would be two
         controls for one action, and two vocabularies for it. -->
    <DiagramViewportControls
      :is-transformed="isTransformed"
      :is-fullscreen="fullscreen.isFullscreen.value"
      :can-fullscreen="fullscreen.isSupported"
      hint="Scroll to zoom · Drag to pan · Click node to inspect · Double-click to expand"
      @reset="fitToView"
      @toggle-fullscreen="fullscreen.toggle"
    />
    <svg
      ref="svgRef"
      class="graph-svg"
      :style="{ visibility: nodes.length > 0 && !hasFitted ? 'hidden' : 'visible' }"
      :viewBox="vb"
      @mousedown.self="onSvgMouseDown"
      @click.self="onBackgroundClick"
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
        <GraphCanvasNode
          :node="n"
          :selected="selectedId === n.id"
          :anchor="isAnchor(n.id)"
          :visual="nodeVisual(n)"
          :expandable="showExpandBadge(n)"
        />
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
