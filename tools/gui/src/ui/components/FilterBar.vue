<script setup lang="ts">
/**
 * A row of "narrow the list to one value of one field" selects.
 *
 * Every filter on a browse surface is the same operation, so it is described as data and
 * rendered once rather than as N hand-written selects that drift apart — one gains an
 * accessible name, another forgets the "All" option, a third orders its values differently.
 *
 * Vocabulary-free by contract: the caller supplies the fields and their options, and this
 * knows only that a filter has a key, a label for its unfiltered state, and some values. It
 * names no ontology, no module and no record type, so any browse surface can mount it.
 */

export interface FilterSpec {
  /** Field key; also the key into the selection object. */
  field: string
  /** The unfiltered choice, e.g. "All types" — also the control's accessible name. */
  allLabel: string
}

defineProps<{
  filters: readonly FilterSpec[]
  /** Selected value per field; empty string means unfiltered. */
  modelValue: Record<string, string>
  /** Selectable values per field, in display order. */
  optionsFor: ReadonlyMap<string, readonly string[]>
}>()

const emit = defineEmits<{ 'update:modelValue': [value: Record<string, string>] }>()

const select = (current: Record<string, string>, field: string, value: string): void => {
  emit('update:modelValue', { ...current, [field]: value })
}
</script>

<template>
  <div class="filter-bar">
    <select
      v-for="filter in filters"
      :key="filter.field"
      class="filter-select"
      :aria-label="filter.allLabel"
      :value="modelValue[filter.field] ?? ''"
      @change="select(modelValue, filter.field, ($event.target as HTMLSelectElement).value)"
    >
      <option value="">
        {{ filter.allLabel }}
      </option>
      <option
        v-for="value in optionsFor.get(filter.field) ?? []"
        :key="value"
        :value="value"
      >
        {{ value }}
      </option>
    </select>
  </div>
</template>

<style scoped>
.filter-bar {
  display: flex; flex-wrap: wrap; gap: 8px; padding: 10px 16px;
  border-bottom: 1px solid #e5e7eb; background: white;
}
.filter-select {
  font-size: 12px; padding: 4px 8px; border: 1px solid #d1d5db; border-radius: 5px;
  background: white; color: #374151;
}
</style>
