<script setup lang="ts">
import { watch } from 'vue'
import type { ViewpointSummary } from '../../domain'
import { viewpointOptionLabel, findViewpointBySlug } from './ViewpointSelect.helpers'

const props = defineProps<{
  modelValue: string | null
  viewpoints: readonly ViewpointSummary[]
}>()
const emit = defineEmits<{
  'update:modelValue': [slug: string | null]
  select: [viewpoint: ViewpointSummary | null]
}>()

const onChange = (event: Event) => {
  const raw = (event.target as HTMLSelectElement).value
  const slug = raw === '' ? null : raw
  emit('update:modelValue', slug)
  emit('select', findViewpointBySlug(props.viewpoints, slug))
}

// Re-emit `select` if the catalog loads after modelValue was already set (e.g. pre-filled
// from an existing diagram's applied viewpoint before the guidance fetch resolves).
watch(() => props.viewpoints, (viewpoints) => {
  if (props.modelValue !== null) emit('select', findViewpointBySlug(viewpoints, props.modelValue))
})
</script>

<template>
  <select
    class="inp viewpoint-select"
    :value="modelValue ?? ''"
    @change="onChange"
  >
    <option value="">
      None (unrestricted)
    </option>
    <option
      v-for="viewpoint in viewpoints"
      :key="viewpoint.slug"
      :value="viewpoint.slug"
    >
      {{ viewpointOptionLabel(viewpoint) }}
    </option>
  </select>
</template>

<style scoped>
/* Self-contained look: this select is embedded in several hosts (graph toolbar,
   diagram views) whose scoped styles cannot reach into it. */
.viewpoint-select {
  max-width: 260px;
  padding: 5px 8px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  background: white;
  font-size: 12px;
  color: #374151;
  outline: none;
  cursor: pointer;
}
.viewpoint-select:focus { border-color: #2563eb; }
</style>
