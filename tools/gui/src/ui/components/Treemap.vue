<script setup lang="ts">
/**
 * A zoomable, pannable treemap of grouped leaves.
 *
 * Domain-agnostic by contract — it receives groups whose leaves already carry their label, colour
 * and weight, and it never imports architecture, assurance, viewpoint or ontology concepts. What a
 * leaf *is*, how it is grouped, what its weight means and where clicking it goes are all the
 * caller's: the architecture browse surface groups entities by domain and sizes them by connection
 * count, the assurance browse surface groups nodes by node type. A component that knew either
 * vocabulary would be wrong for the other one first.
 *
 * Two slots keep the last vocabulary out: `glyph` draws whatever mark a leaf deserves at the
 * position given, and `tooltip` renders whatever the caller wants to say about a hovered leaf.
 *
 * Geometry and the legibility thresholds live in `Treemap.helpers`, where they are tested; the
 * gestures — pan, zoom, hover, press-to-select — live in `useTreemapInteraction`.
 */
import { computed, ref, watch } from 'vue'
import { hierarchy, treemap, type HierarchyRectangularNode } from 'd3-hierarchy'
import { useTreemapInteraction } from '../composables/useTreemapInteraction'
import {
  groupFontSize,
  leafVisuals,
  showGroupLabel,
  sizeOf,
  type TreemapGroup,
  type TreemapLeaf,
} from './Treemap.helpers'

type Node = { children: TreemapGroup[] } | TreemapGroup | TreemapLeaf

const props = defineProps<{
  groups: TreemapGroup[]
  /** The line above the canvas explaining what size and grouping mean here. */
  note?: string
}>()

const emit = defineEmits<{ select: [key: string] }>()

const hostRef = ref<HTMLElement | null>(null)
const svgRef = ref<SVGSVGElement | null>(null)

const {
  size, zoom, viewBox, transform, tooltipLeaf, tooltipPos,
  resetView, clearTooltip, queueTooltip, zoomByButton, onWheel, startPan,
} = useTreemapInteraction<TreemapLeaf>(hostRef, svgRef, (key) => emit('select', key))

const layout = computed(() => {
  const root = hierarchy<Node>({ children: props.groups }, (node) =>
    'children' in node ? node.children : undefined,
  ).sum((node) => ('value' in node ? sizeOf(node.value) : 0))
  return treemap<Node>()
    .size([Math.max(size.value.width, 320), Math.max(size.value.height, 320)])
    .paddingOuter(10)
    .paddingTop((node) => (node.depth === 1 ? 26 : 3))
    .paddingInner(4)
    .round(true)(root)
})

const groupRects = computed(() =>
  ((layout.value.children ?? []) as HierarchyRectangularNode<TreemapGroup>[]).map((group) => {
    const width = group.x1 - group.x0
    const height = group.y1 - group.y0
    return {
      key: group.data.name,
      name: group.data.name,
      color: group.data.color,
      x: group.x0,
      y: group.y0,
      width,
      height,
      showLabel: showGroupLabel(width, height, zoom.value),
      fontSize: groupFontSize(width, height),
    }
  }),
)

const leaves = computed(() =>
  (layout.value.leaves() as HierarchyRectangularNode<TreemapLeaf>[])
    .filter((leaf) => leaf.data.key != null)
    .map((leaf) => {
      const width = leaf.x1 - leaf.x0
      const height = leaf.y1 - leaf.y0
      return {
        key: leaf.data.key,
        leaf: leaf.data,
        color: leaf.data.color,
        x: leaf.x0,
        y: leaf.y0,
        width,
        height,
        ...leafVisuals(width, height, leaf.data.label, zoom.value),
      }
    }),
)

watch(() => props.groups, resetView)
</script>

<template>
  <div
    ref="hostRef"
    class="treemap-card"
  >
    <div class="treemap-topbar">
      <div class="treemap-note">
        {{ props.note }}
      </div>
      <div class="treemap-controls">
        <button
          class="control-btn"
          title="Zoom out"
          @click="zoomByButton(-0.35)"
        >
          −
        </button>
        <button
          class="control-btn"
          title="Reset zoom and pan"
          @click="resetView"
        >
          {{ zoom.toFixed(1) }}x
        </button>
        <button
          class="control-btn"
          title="Zoom in"
          @click="zoomByButton(0.35)"
        >
          +
        </button>
      </div>
    </div>
    <svg
      ref="svgRef"
      class="treemap-svg"
      :viewBox="viewBox"
      preserveAspectRatio="xMidYMid meet"
      @wheel.prevent="onWheel"
      @mousedown="startPan"
    >
      <rect
        class="interaction-bg"
        x="0"
        y="0"
        :width="size.width"
        :height="size.height"
      />
      <g :transform="transform">
        <g
          v-for="group in groupRects"
          :key="group.key"
        >
          <rect
            class="group-shell"
            :x="group.x"
            :y="group.y"
            :width="group.width"
            :height="group.height"
            :fill="group.color"
            fill-opacity="0.16"
            :stroke="group.color"
          />
          <text
            v-if="group.showLabel"
            class="group-label"
            :x="group.x + 10"
            :y="group.y + group.fontSize + 5"
            :font-size="group.fontSize"
          >{{ group.name }}</text>
        </g>
        <g
          v-for="tile in leaves"
          :key="tile.key"
          :data-leaf-id="tile.key"
          @mouseenter="queueTooltip(tile.leaf, $event.clientX, $event.clientY)"
          @mousemove="queueTooltip(tile.leaf, $event.clientX, $event.clientY)"
          @mouseleave="clearTooltip"
        >
          <rect
            class="leaf-block"
            :x="tile.x"
            :y="tile.y"
            :width="tile.width"
            :height="tile.height"
            :fill="tile.color"
          />
          <g class="leaf-copy">
            <slot
              v-if="tile.showIcon"
              name="glyph"
              :leaf="tile.leaf"
              :x="tile.x + tile.left"
              :y="tile.y + Math.max(6, (tile.height - tile.iconSize) / 2 - (tile.showName ? 5 : 0))"
              :size="tile.iconSize"
            />
            <text
              v-if="tile.showName"
              class="leaf-name"
              :x="tile.x + tile.textX"
              :y="tile.y + 8 + tile.nameSize"
              :font-size="tile.nameSize"
            >{{ tile.label }}</text>
            <text
              v-if="tile.showMeta && tile.leaf.meta"
              class="leaf-meta"
              :x="tile.x + tile.textX"
              :y="tile.y + 10 + tile.nameSize + tile.metaSize + 4"
              :font-size="tile.metaSize"
            >{{ tile.leaf.meta }}</text>
          </g>
        </g>
      </g>
    </svg>
    <div
      v-if="tooltipLeaf"
      class="leaf-tooltip"
      :style="{ left: `${tooltipPos.x}px`, top: `${tooltipPos.y}px` }"
    >
      <slot
        name="tooltip"
        :leaf="tooltipLeaf"
      />
    </div>
  </div>
</template>

<style scoped>
.treemap-card {
  background: white; border: 1px solid #e5e7eb; border-radius: 10px;
  overflow: hidden; min-height: 620px; position: relative;
}
.treemap-topbar, .treemap-controls { display: flex; align-items: center; }
.treemap-topbar {
  justify-content: space-between; gap: 14px; padding: 10px 14px;
  border-bottom: 1px solid #e5e7eb; background: #f8fafc;
}
.treemap-note { font-size: 12px; color: #6b7280; }
.treemap-controls { gap: 6px; }
.control-btn {
  min-width: 34px; padding: 6px 9px; border: 1px solid #d1d5db; border-radius: 6px;
  background: white; color: #374151; cursor: pointer; font-size: 12px;
}
.control-btn:hover { background: #f3f4f6; }
.treemap-svg { display: block; width: 100%; height: 620px; cursor: grab; }
.treemap-svg:active { cursor: grabbing; }
.interaction-bg { fill: #fff; }
.group-shell { stroke-width: 1.5; rx: 10; }
.group-label { font-weight: 700; letter-spacing: .02em; pointer-events: none; }
.leaf-block { cursor: pointer; stroke: rgba(255, 255, 255, 0.9); stroke-width: 1.5; }
.leaf-block:hover { filter: brightness(0.98) saturate(1.08); }
.leaf-copy { cursor: pointer; pointer-events: none; }
.leaf-name, .leaf-meta { fill: #1f2937; }
.leaf-name { font-weight: 600; }
.leaf-meta { opacity: .8; }
.leaf-tooltip {
  position: absolute;
  z-index: 2;
  min-width: 220px;
  max-width: 260px;
  padding: 10px 12px;
  border: 1px solid #d1d5db;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.98);
  box-shadow: 0 10px 30px rgba(15, 23, 42, 0.14);
  pointer-events: none;
}
</style>
