<script setup lang="ts">
/**
 * Canvas-beside-sidebar with a draggable divider — the layout every diagram detail surface uses, and
 * the stress-analysis workspace, whose tables sit on the left of its canvas (`edge`).
 *
 * It owns the grid, the splitter, and the drag: the width lives in one place, so the two halves
 * can never disagree about it, and a host that wants this layout gets the resize behaviour by
 * construction rather than by remembering to wire a composable to a template ref. The splitter
 * takes focus and moves by ← and → as well.
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
    /** The largest share of the width the sidebar may take. */
    maxShare?: number
    /** Which side the sidebar sits on. */
    edge?: 'left' | 'right'
    /** Gives the canvas the full width and hides the splitter, for a sidebar that only exists
     * once the reader selects something. The canvas stays mounted either way — collapsing must
     * not re-fetch or reset what the reader is looking at. */
    sidebarCollapsed?: boolean
  }>(),
  { initialWidth: 320, minWidth: 260, maxWidth: 520, maxShare: 0.45, edge: 'right', sidebarCollapsed: false },
)

const gridRef = ref<HTMLElement | null>(null)
const { gridStyle, startResize, nudge } = useSidebarResize(gridRef, {
  initialWidth: props.initialWidth,
  minWidth: props.minWidth,
  maxWidth: props.maxWidth,
  maxShare: props.maxShare,
  edge: props.edge,
})
</script>

<template>
  <div
    ref="gridRef"
    class="main-grid"
    :class="{ 'main-grid--full-canvas': sidebarCollapsed, 'main-grid--left': edge === 'left' }"
    :style="gridStyle"
  >
    <slot
      v-if="edge === 'left' && !sidebarCollapsed"
      name="sidebar"
    />
    <slot
      v-if="edge === 'right'"
      name="canvas"
    />

    <div
      v-if="!sidebarCollapsed"
      class="sidebar-splitter"
      role="separator"
      tabindex="0"
      aria-orientation="vertical"
      aria-label="Resize sidebar"
      title="Drag, or press ← and →"
      data-testid="splitter"
      @mousedown="startResize"
      @keydown="nudge"
    />

    <slot
      v-if="edge === 'left'"
      name="canvas"
    />
    <slot
      v-if="edge === 'right' && !sidebarCollapsed"
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
.main-grid--left { grid-template-columns: var(--sidebar-width) 12px minmax(0, 1fr); }
.main-grid--full-canvas { grid-template-columns: minmax(0, 1fr); }
@media (max-width: 800px) { .main-grid, .main-grid--left { grid-template-columns: 1fr; } }

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
  background: var(--border);
  transition: background-color 0.15s ease;
}
.sidebar-splitter:hover::before, .sidebar-splitter:focus-visible::before { background: var(--accent-border); }
.sidebar-splitter:focus-visible { outline: none; }
@media (max-width: 800px) {
  .sidebar-splitter { display: none; }
}
</style>
