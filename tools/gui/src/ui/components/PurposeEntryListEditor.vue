<script setup lang="ts">
/**
 * One purpose list — stakeholders or concerns — as chips: prose typed in, or an element picked from the
 * model. Used for a diagram's own lines and for a viewpoint's, which share the shape. A referenced element
 * shows its name once picked here; one loaded from a stored list shows its name where the caller knows it
 * (`names`), else its id.
 */
import { ref } from 'vue'
import type { EntityDisplayInfo } from '../../domain'
import { type PurposeEntry, referencedId, withEntry, withoutEntry } from '../../domain/purposeLines'
import EntityPickerInput from './EntityPickerInput.vue'

const props = withDefaults(defineProps<{
  modelValue: readonly PurposeEntry[]
  label: string
  proseHint: string
  names?: Readonly<Record<string, string>>
}>(), { names: () => ({}) })
const emit = defineEmits<{ 'update:modelValue': [value: PurposeEntry[]] }>()

const picked = ref<Record<string, string>>({})
const prose = ref('')

const chipText = (entry: PurposeEntry): string => {
  const id = referencedId(entry)
  return id === undefined ? String(entry) : (picked.value[id] ?? props.names[id] ?? id)
}
const addProse = () => {
  emit('update:modelValue', withEntry(props.modelValue, prose.value))
  prose.value = ''
}
const addReference = (entity: EntityDisplayInfo) => {
  picked.value = { ...picked.value, [entity.artifact_id]: entity.name }
  emit('update:modelValue', withEntry(props.modelValue, { ref: entity.artifact_id }))
}
</script>

<template>
  <div
    class="purpose-list"
    :data-testid="`purpose-list-${label.toLowerCase()}`"
  >
    <span class="purpose-label">{{ label }}</span>
    <span
      v-for="(entry, index) in modelValue"
      :key="`${index}-${chipText(entry)}`"
      class="chip"
      :class="{ 'chip--ref': referencedId(entry) !== undefined }"
    >
      {{ chipText(entry) }}
      <button
        type="button"
        class="chip-x"
        :aria-label="`remove ${chipText(entry)}`"
        @click="emit('update:modelValue', withoutEntry(modelValue, index))"
      >✕</button>
    </span>
    <input
      v-model="prose"
      class="prose-input"
      :placeholder="proseHint"
      :aria-label="`${label}: add in words`"
      @keydown.enter.prevent="addProse"
    >
    <EntityPickerInput
      placeholder="…or pick an element"
      close-on-select
      @select="addReference"
    />
  </div>
</template>

<style scoped>
.purpose-list { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin-bottom: 8px; }
.purpose-label { font-size: 12px; font-weight: 600; min-width: 72px; }
.chip {
  display: inline-flex; align-items: center; gap: 4px; border-radius: 999px; padding: 2px 4px 2px 10px;
  font-size: 12px; background: var(--surface); border: 1px solid var(--border-strong);
}
.chip--ref { background: var(--indigo-soft); color: var(--indigo-text); border-color: transparent; }
.chip-x { appearance: none; border: none; background: none; cursor: pointer; font-size: 12px; padding: 2px 4px; }
.prose-input { font-size: 12px; padding: 3px 6px; min-width: 180px; }
</style>
