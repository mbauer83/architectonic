<script setup lang="ts">
/**
 * What only a hand-drawn picture has, as the server names it (`hand_drawn` on the diagram read): boxes by
 * their labels, elements by their names, relations as "Name → Name (type)". Collapsed until asked for, so the
 * sentence above it reads first. Nothing renders where the read names nothing.
 */
import { computed } from 'vue'
import type { HandDrawn } from '../../domain/schemas/handDrawn'

const props = defineProps<{ handDrawn?: HandDrawn | undefined }>()

/** One line per construct, in the order a reader meets them on the picture: boxes, elements, relations. */
const lines = computed((): string[] => {
  const drawn = props.handDrawn
  if (!drawn) return []
  return [
    ...drawn.boxes.map((box) => `Box "${box}"`),
    ...drawn.elements.map((element) => `Element "${element}"`),
    ...drawn.relations.map((relation) =>
      `${relation.source} → ${relation.target}${relation.type ? ` (${relation.type})` : ''}`),
    ...drawn.directions.map((direction) => `Laid out ${direction}`),
  ]
})
</script>

<template>
  <details
    v-if="lines.length"
    class="hand-drawn"
    data-testid="hand-drawn-details"
  >
    <summary>What only the hand-drawn picture has</summary>
    <ul>
      <li
        v-for="line in lines"
        :key="line"
      >
        {{ line }}
      </li>
    </ul>
  </details>
</template>

<style scoped>
.hand-drawn { margin-top: 4px; }
.hand-drawn summary { cursor: pointer; }
.hand-drawn ul { margin: 4px 0 0; padding-left: 20px; }
</style>
