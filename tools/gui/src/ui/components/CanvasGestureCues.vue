<script setup lang="ts">
/**
 * What a press or a drop on the canvas is about to do, shown where it will happen and at screen size
 * whatever the zoom: the side of an element's edge band under the pointer, lit blue because a drag from
 * it draws a relation (01·10, 03·8); and the box or element an element being moved would land in, lit
 * with words — "Into Business", "Nest in …" (03·9). A shape that would refuse it is not lit.
 */
import { computed } from 'vue'
import { sideOf } from '../../domain/layout/edgeBand'
import type { HoveredSide } from '../composables/useContentGestures'
import type { LitTarget } from '../composables/useDropFeedback'

const props = defineProps<{ side: HoveredSide | null; lit: LitTarget | null }>()

/** The lit side as a bar on screen. */
const bar = computed(() => {
  const hovered = props.side
  if (!hovered) return null
  const [from, to] = sideOf(hovered.at, hovered.side)
  const across = from.x === to.x
  return {
    left: `${from.x - (across ? 2 : 0)}px`, top: `${from.y - (across ? 0 : 2)}px`,
    width: across ? '4px' : `${to.x - from.x}px`, height: across ? `${to.y - from.y}px` : '4px',
  }
})
</script>

<template>
  <div
    v-if="bar"
    class="cue-side"
    data-testid="edge-side"
    :data-side="side?.side"
    :style="bar"
  />
  <template v-if="lit">
    <div
      class="cue-drop"
      data-testid="drop-target"
      :style="{
        left: `${lit.at.left - 3}px`, top: `${lit.at.top - 3}px`,
        width: `${lit.at.right - lit.at.left + 6}px`, height: `${lit.at.bottom - lit.at.top + 6}px`,
      }"
    />
    <span
      class="cue-words"
      data-testid="drop-target-words"
      :style="{ left: `${lit.at.left + 4}px`, top: `${lit.at.top + 4}px` }"
    >{{ lit.words }}</span>
  </template>
</template>

<style scoped>
/* Drawn on the paper's colours, fixed like the paper, and never in the way of a press. */
.cue-side, .cue-drop, .cue-words { position: fixed; pointer-events: none; z-index: 5; }
.cue-side { background: var(--paper-accent); border-radius: 2px; }
.cue-drop {
  border: 2px dashed var(--paper-accent); border-radius: 4px; background: var(--paper-accent-soft);
}
.cue-words {
  padding: 1px 6px; border: 1px solid var(--paper-accent); border-radius: 3px; background: var(--paper);
  color: var(--paper-accent); font: 600 11px system-ui, sans-serif; white-space: nowrap;
}
</style>
