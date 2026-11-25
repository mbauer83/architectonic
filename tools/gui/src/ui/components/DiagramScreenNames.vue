<script setup lang="ts">
/**
 * Names written at screen size while the picture's own text is too small to read (04·1, 04·6): on a
 * large diagram zoomed out, a box is a rectangle with no word readable and a reading is a scatter of
 * lit specks. With a reading, its elements are named; without one, the boxes in the window are
 * (`screenNamesOf`). They sit over the canvas as HTML, so no export carries them, and give way as soon
 * as the picture's text can be read again.
 */
import { computed, ref } from 'vue'
import type { Point } from '../../domain/layout/geometry'
import type { OverviewMark } from '../lib/diagramOverview'
import { pictureTextSizeOf } from '../lib/diagramOverview'
import { screenNamesOf } from '../lib/screenNames'
import { useElementSize } from '../composables/useElementSize'

const props = withDefaults(defineProps<{
  /** The reading's elements: named first, and alone, while there is a reading. */
  marks: readonly OverviewMark[]
  /** Every element the picture draws, with its name: named while there is no reading. */
  boxes?: readonly OverviewMark[]
  /** The element the picture's `<svg>` is mounted in: what its text size is read from. */
  picture: HTMLElement | null
  scale: number
  toWindow: (point: Point) => Point
}>(), { boxes: () => [] })

const root = ref<HTMLElement | null>(null)
const canvas = useElementSize(() => root.value?.parentElement)

const names = computed(() => {
  const svg = props.picture?.querySelector('svg')
  const size = svg && (props.marks.length > 0 || props.boxes.length > 0) ? pictureTextSizeOf(svg) : null
  return screenNamesOf({
    reading: props.marks, boxes: props.boxes, textPixels: size === null ? null : size * props.scale,
    toWindow: props.toWindow, window: { width: canvas.width.value, height: canvas.height.value },
  })
})
</script>

<template>
  <div
    ref="root"
    class="screen-names"
    :data-testid="marks.length > 0 ? 'reading-names' : 'box-names'"
  >
    <span
      v-for="name in names"
      :key="name.id"
      class="screen-name"
      :class="[name.place, { selected: name.selected }]"
      :style="{ left: `${name.at.x}px`, top: `${name.at.y}px` }"
    >{{ name.name }}</span>
  </div>
</template>

<style scoped>
.screen-names { position: absolute; inset: 0; overflow: hidden; pointer-events: none; z-index: 1; }
/* Drawn on the paper, so in the paper's fixed colours in either theme. */
.screen-name {
  position: absolute; max-width: 220px; white-space: nowrap;
  overflow: hidden; text-overflow: ellipsis; padding: 1px 6px; border-radius: 4px; font-size: 11.5px;
  font-weight: 600; background: var(--paper-handle); color: var(--paper-ink); border: 1px solid var(--paper-rule);
}
.screen-name.above { transform: translate(-50%, calc(-100% - 4px)); }
.screen-name.on { transform: translate(-50%, -50%); opacity: 0.92; }
.screen-name.selected {
  background: var(--paper-accent); border-color: var(--paper-accent); color: var(--paper-handle);
}
@media print { .screen-names { display: none; } }
</style>
