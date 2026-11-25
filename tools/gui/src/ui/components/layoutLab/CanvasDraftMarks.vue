<script setup lang="ts">
/**
 * The draft marker (sketch 03·4, Q17): a small light-grey "d" in the top right corner of every shape that
 * draws a draft, and nothing else — quiet enough to sketch candidate architectures with. It is the
 * canvas's own mark, drawn over the picture, so no download carries it; a screen reader hears "draft"
 * with the shape's name instead (`useCanvasFocus`), and the mark itself is hidden from it.
 */
import { computed } from 'vue'
import type { ArrangementSession } from '../../composables/useArrangementSession'

/** *drafts*: the shapes that draw a draft, by alias. */
const props = defineProps<{ session: ArrangementSession; drafts: ReadonlySet<string> }>()

/** How far in from the corner the mark sits, and how tall it is, in the picture's own units. */
const INSET = 4
const SIZE = 9

const corners = computed(() => {
  const where = props.session.placement.value
  return where ? [...props.drafts].flatMap((alias) => {
    const extent = where.elements.get(alias) ?? where.boxes.get(alias)
    return extent ? [{ alias, x: extent.right - INSET, y: extent.top + INSET + SIZE }] : []
  }) : []
})
</script>

<template>
  <g
    class="draft-marks"
    data-testid="draft-marks"
    aria-hidden="true"
  >
    <text
      v-for="corner in corners"
      :key="corner.alias"
      class="draft-mark"
      :data-draft="corner.alias"
      :x="corner.x"
      :y="corner.y"
      :font-size="SIZE"
      text-anchor="end"
    >
      d
    </text>
  </g>
</template>

<style scoped>
/* Drawn on the paper, so in the paper's fixed colours in either theme. */
.draft-mark { fill: var(--paper-rule); font-family: system-ui, sans-serif; pointer-events: none; }
</style>
