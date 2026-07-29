<script setup lang="ts">
import type { SelectionMode } from '../../domain/viewpointDefinitionDraft'

/** Scope and query are ALTERNATIVE selection mechanisms — exactly one is active. This
 * switch states which, right where the Scope/Query tabs are chosen; the inactive layer's
 * tab is disabled (its content is kept as history, never silently merged in). */
defineProps<{
  modelValue: SelectionMode
}>()
const emit = defineEmits<{ 'update:modelValue': [value: SelectionMode] }>()
</script>

<template>
  <div class="mode-switch">
    <span class="mode-label">Selection:</span>
    <label class="mode-option">
      <input
        type="radio"
        value="scope"
        :checked="modelValue === 'scope'"
        @change="emit('update:modelValue', 'scope')"
      >
      Simple (entity types — Scope tab)
    </label>
    <label class="mode-option">
      <input
        type="radio"
        value="query"
        :checked="modelValue === 'query'"
        @change="emit('update:modelValue', 'query')"
      >
      Extended (query — Query tab)
    </label>
    <span class="mode-hint">
      exactly one is active; the other layer is kept but never executes
    </span>
  </div>
</template>

<style scoped>
.mode-switch {
  display: flex; align-items: center; flex-wrap: wrap; gap: 10px;
  padding: 6px 0; font-size: 12.5px; color: #374151;
}
.mode-label { font-weight: 600; }
.mode-option { display: inline-flex; align-items: center; gap: 4px; cursor: pointer; }
.mode-hint { color: #9ca3af; font-size: 11.5px; }
</style>
