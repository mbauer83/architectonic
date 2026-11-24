<script setup lang="ts">
/**
 * The names of the reading's elements, written at screen size while the picture's own text is too
 * small to read (owner, 04·6): on a large diagram fitted to the window a reading is a scatter of lit
 * specks, and these say what they are. They sit over the canvas as HTML, so no export carries them,
 * and give way as soon as the picture's text can be read again.
 */
import { computed } from 'vue'
import type { Point } from '../../domain/layout/geometry'
import type { OverviewMark } from '../lib/diagramOverview'
import { pictureTextSizeOf } from '../lib/diagramOverview'

const props = defineProps<{
  marks: readonly OverviewMark[]
  /** The element the picture's `<svg>` is mounted in: what its text size is read from. */
  picture: HTMLElement | null
  scale: number
  toWindow: (point: Point) => Point
}>()

/** Text smaller than this on screen is not read; under it, the reading's names are written. */
const LEGIBLE_PIXELS = 6
/** More than this many names is a wall of labels, not help: the panel's lists name the rest. */
const MOST = 40

const names = computed(() => {
  const svg = props.picture?.querySelector('svg')
  const size = svg && props.marks.length > 0 ? pictureTextSizeOf(svg) : null
  if (size === null || size * props.scale >= LEGIBLE_PIXELS) return []
  return props.marks.slice(0, MOST).map((mark) => ({
    ...mark,
    at: props.toWindow({ x: (mark.extent.left + mark.extent.right) / 2, y: mark.extent.top }),
  }))
})
</script>

<template>
  <div
    v-if="names.length > 0"
    class="reading-names"
    data-testid="reading-names"
  >
    <span
      v-for="name in names"
      :key="name.id"
      class="reading-name"
      :class="{ selected: name.selected }"
      :style="{ left: `${name.at.x}px`, top: `${name.at.y}px` }"
    >{{ name.name }}</span>
  </div>
</template>

<style scoped>
.reading-names { position: absolute; inset: 0; overflow: hidden; pointer-events: none; z-index: 1; }
/* Drawn on the paper, so in the paper's fixed colours in either theme. */
.reading-name {
  position: absolute; transform: translate(-50%, calc(-100% - 4px)); max-width: 220px; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; padding: 1px 6px; border-radius: 4px; font-size: 11.5px;
  font-weight: 600; background: var(--paper-handle); color: var(--paper-ink); border: 1px solid var(--paper-rule);
}
.reading-name.selected {
  background: var(--paper-accent); border-color: var(--paper-accent); color: var(--paper-handle);
}
@media print { .reading-names { display: none; } }
</style>
