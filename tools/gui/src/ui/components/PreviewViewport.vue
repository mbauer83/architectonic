<script setup lang="ts">
import { toRef, useTemplateRef } from 'vue'
import { usePanZoom } from '../composables/usePanZoom'

const props = defineProps<{ resetSignal?: unknown }>()

const viewport = useTemplateRef<HTMLElement>('viewport')
const { canvasStyle, isTransformed, resetView, startDrag } = usePanZoom(
  viewport,
  toRef(props, 'resetSignal'),
)

defineExpose({ resetView })
</script>

<template>
  <div
    ref="viewport"
    class="preview-viewport"
    @mousedown="startDrag"
    @dblclick="resetView"
  >
    <div
      class="preview-canvas"
      :style="canvasStyle"
    >
      <slot />
    </div>
    <button
      v-if="isTransformed"
      class="reset-btn"
      @click.stop="resetView"
    >
      ⊙ Reset
    </button>
    <div class="zoom-hint">
      Scroll to zoom · Drag to pan · Double-click to reset
    </div>
  </div>
</template>

<style scoped>
.preview-viewport {
  position: relative; overflow: hidden; cursor: grab; user-select: none;
  background: #f8fafc; border: 1px solid #e5e7eb; border-radius: 6px;
  min-height: 200px; height: clamp(360px, 70vh, 900px);
}
@media (max-width: 800px) { .preview-viewport { height: clamp(300px, 60vh, 700px); } }
.preview-viewport:active { cursor: grabbing; }
/* The canvas fills the viewport so its content can be sized against it: a diagram opens whole and
   zoom magnifies from there, rather than opening at native size with most of it off-screen. */
.preview-canvas {
  width: 100%; height: 100%;
  display: flex; align-items: center; justify-content: center;
}
.reset-btn { position: absolute; top: 8px; right: 8px; padding: 4px 10px; background: rgba(255,255,255,.92); border: 1px solid #d1d5db; border-radius: 5px; font-size: 12px; cursor: pointer; color: #374151; }
.reset-btn:hover { background: white; }
.zoom-hint { position: absolute; bottom: 6px; left: 50%; transform: translateX(-50%); font-size: 11px; color: #9ca3af; background: rgba(255,255,255,.8); padding: 2px 8px; border-radius: 4px; pointer-events: none; white-space: nowrap; }
</style>
