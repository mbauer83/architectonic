<script setup lang="ts">
import { computed, watch } from 'vue'
import type { ViewpointSummary } from '../../domain'
import { NOT_INTENDED_NOTE, viewpointOptionLabel, viewpointOptions, findViewpointBySlug } from './ViewpointSelect.helpers'

const props = defineProps<{
  modelValue: string | null
  viewpoints: readonly ViewpointSummary[]
  /** The diagram type being authored: viewpoints intended for it are listed first, the rest marked. */
  diagramType?: string
}>()
const options = computed(() => viewpointOptions(props.viewpoints, props.diagramType))
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
      v-for="{ viewpoint, suited } in options"
      :key="viewpoint.slug"
      :value="viewpoint.slug"
      :class="{ 'not-intended': !suited }"
    >
      {{ viewpointOptionLabel(viewpoint) }}{{ suited ? '' : ` — ${NOT_INTENDED_NOTE}` }}
    </option>
  </select>
</template>

<style scoped>
/* Self-contained look: this select is embedded in several hosts (graph toolbar,
   diagram views) whose scoped styles cannot reach into it. */
.viewpoint-select {
  max-width: 260px;
  padding: 5px 8px;
  border: 1px solid var(--border-strong);
  border-radius: 6px;
  background: var(--surface);
  font-size: 12px;
  color: var(--text-2);
  outline: none;
  cursor: pointer;
}
.viewpoint-select:focus { border-color: var(--accent); }
.not-intended { color: var(--faint); }
</style>
