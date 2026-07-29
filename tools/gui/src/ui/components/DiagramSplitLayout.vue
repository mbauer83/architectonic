<script setup lang="ts">
/**
 * Canvas-beside-sidebar with a draggable divider — the layout every diagram detail surface uses.
 *
 * It owns the grid, the splitter, and the drag: the width lives in one place, so the two halves
 * can never disagree about it, and a host that wants this layout gets the resize behaviour by
 * construction rather than by remembering to wire a composable to a template ref.
 *
 * Below the mobile breakpoint the columns stack and the splitter disappears — dragging a divider
 * is not a gesture that makes sense on a narrow viewport.
 */
import { ref } from 'vue'
import { useSidebarResize } from '../composables/useSidebarResize'

const props = withDefaults(
  defineProps<{
    initialWidth?: number
    minWidth?: number
    maxWidth?: number
    /** Gives the canvas the full width and hides the splitter, for a sidebar that only exists
     * once the reader selects something. The canvas stays mounted either way — collapsing must
     * not re-fetch or reset what the reader is looking at. */
    sidebarCollapsed?: boolean
  }>(),
  { initialWidth: 320, minWidth: 260, maxWidth: 520, sidebarCollapsed: false },
)

const gridRef = ref<HTMLElement | null>(null)
const { gridStyle, startResize } = useSidebarResize(gridRef, {
  initialWidth: props.initialWidth,
  minWidth: props.minWidth,
  maxWidth: props.maxWidth,
})
</script>

<template>
  <div
    ref="gridRef"
    class="main-grid"
    :class="{ 'main-grid--full-canvas': sidebarCollapsed }"
    :style="gridStyle"
  >
    <slot name="canvas" />

    <div
      v-if="!sidebarCollapsed"
      class="sidebar-splitter"
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize sidebar"
      @mousedown="startResize"
    />

    <slot
      v-if="!sidebarCollapsed"
      name="sidebar"
    />
  </div>
</template>

<style scoped>
.main-grid {
  --sidebar-width: 320px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) 12px var(--sidebar-width);
  gap: 0;
  align-items: start;
}
.main-grid--full-canvas { grid-template-columns: minmax(0, 1fr); }
@media (max-width: 800px) { .main-grid { grid-template-columns: 1fr; } }

.sidebar-splitter {
  position: sticky;
  top: 16px;
  height: clamp(420px, 78vh, 980px);
  cursor: col-resize;
  background: transparent;
}
.sidebar-splitter::before {
  content: '';
  display: block;
  width: 4px;
  height: 100%;
  margin: 0 auto;
  border-radius: 999px;
  background: #e5e7eb;
  transition: background-color 0.15s ease;
}
.sidebar-splitter:hover::before { background: #93c5fd; }
@media (max-width: 800px) {
  .sidebar-splitter { display: none; }
}
</style>
