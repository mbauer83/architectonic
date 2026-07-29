<script setup lang="ts">
import { computed } from 'vue'
import glyphs from '../lib/archimateGlyphs.json'

const props = withDefaults(defineProps<{
  type: string
  x?: number
  y?: number
  size?: number
}>(), {
  x: 0,
  y: 0,
  size: 16,
})

const kind = computed(() => glyphs.types[props.type as keyof typeof glyphs.types] ?? 'generic')
const markup = computed(() => glyphs.kinds[kind.value as keyof typeof glyphs.kinds] ?? glyphs.kinds.generic)
const x = computed(() => props.x)
const y = computed(() => props.y)
const size = computed(() => props.size)
</script>

<template>
  <svg
    xmlns="http://www.w3.org/2000/svg"
    :x="x"
    :y="y"
    :width="size"
    :height="size"
    viewBox="0 0 16 16"
    fill="none"
    stroke="currentColor"
    stroke-width="1.3"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <g v-html="markup" />
  </svg>
</template>
