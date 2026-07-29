<script setup lang="ts">
/**
 * Value input for an entity-reference condition path (currently the reserved `id` path):
 * an entity picker over the real repository instead of a raw id text field. Works in two
 * modes — scalar (`eq`/`neq`, one id) and list (`in`/`not_in`, a set of ids shown as
 * removable chips). Freshly picked ids show the entity's name; ids loaded from a saved
 * definition (name not known here) show the id itself, matching the parameter prompt.
 */
import { computed, ref } from 'vue'
import type { EntityDisplayInfo } from '../../domain'
import EntityPickerInput from './EntityPickerInput.vue'

const props = withDefaults(defineProps<{
  modelValue: string | readonly string[]
  multiple?: boolean
  placeholder?: string
}>(), { multiple: false, placeholder: 'select an entity' })
const emit = defineEmits<{ 'update:modelValue': [value: string | string[]] }>()

/** id -> display name for ids picked this session; loaded ids fall back to the raw id. */
const labels = ref<Record<string, string>>({})
const labelFor = (id: string) => labels.value[id] ?? id

const selectedIds = computed<string[]>(() => {
  const value = props.modelValue
  if (typeof value === 'string') return value.length > 0 ? [value] : []
  return value.map((id) => String(id))
})
const excludedIds = computed(() => new Set(selectedIds.value))

const onSelect = (entity: EntityDisplayInfo) => {
  labels.value = { ...labels.value, [entity.artifact_id]: entity.name }
  if (props.multiple) {
    if (!selectedIds.value.includes(entity.artifact_id)) emit('update:modelValue', [...selectedIds.value, entity.artifact_id])
  } else {
    emit('update:modelValue', entity.artifact_id)
  }
}

const remove = (id: string) => {
  if (props.multiple) emit('update:modelValue', selectedIds.value.filter((v) => v !== id))
  else emit('update:modelValue', '')
}
</script>

<template>
  <span class="entity-ref">
    <span
      v-for="id in selectedIds"
      :key="id"
      class="ref-chip"
    >
      {{ labelFor(id) }}
      <button
        type="button"
        class="ref-chip-x"
        :aria-label="`remove ${labelFor(id)}`"
        @click="remove(id)"
      >✕</button>
    </span>
    <EntityPickerInput
      :placeholder="placeholder"
      :excluded-ids="excludedIds"
      close-on-select
      @select="onSelect"
    />
  </span>
</template>

<style scoped>
.entity-ref { display: inline-flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.ref-chip {
  display: inline-flex; align-items: center; gap: 5px; background: #eef2ff; color: #4338ca;
  border-radius: 999px; padding: 2px 4px 2px 10px; font-size: 12px; font-weight: 500;
}
.ref-chip-x {
  appearance: none; border: none; background: none; color: #6366f1; cursor: pointer;
  font-size: 12px; line-height: 1; padding: 2px 4px; border-radius: 999px;
}
.ref-chip-x:hover { background: #c7d2fe; color: #3730a3; }
</style>
