<script setup lang="ts">
/**
 * One control per classification level the scratchpad's meta-ontology declares, in declared order.
 *
 * The ladder arrives with the scratchpad, so this renders whatever it is given: how many levels
 * there are, what they are called and what each offers are the ontology module's to say. Each
 * control offers what the level above allows.
 *
 * The note's area is advice, not a filter. What the area permits is offered first; everything else
 * is still offered, grouped as outside the area — choosing it is allowed and earns a warning.
 */
import { computed } from 'vue'
import type { Area, ClassificationLevel, Note } from '../../domain/schemas/scratchpads'
import { optionsAt, valueAt } from '../composables/scratchpadClassification'

const props = defineProps<{
  note: Note
  levels: readonly ClassificationLevel[]
  /** The area the note sits in, or `null` in the margin, where everything is permitted. */
  area: Area | null
}>()
const emit = defineEmits<{
  (event: 'refine-note', payload: { id: string; levelId: string; value: string }): void
  (event: 'unrefine-note', payload: { id: string; levelId: string }): void
}>()

const controls = computed(() => props.levels.map((level) => {
  const offered = optionsAt(props.note, level, props.levels, props.area)
  return {
    level,
    value: valueAt(props.note, level) ?? '',
    inside: offered.filter((option) => !option.outsideArea),
    outside: offered.filter((option) => option.outsideArea),
  }
}))

const areaName = computed(() => props.area?.label || props.area?.id || 'this area')

const onChoose = (levelId: string, value: string): void => {
  if (value) emit('refine-note', { id: props.note.id, levelId, value })
  else emit('unrefine-note', { id: props.note.id, levelId })
}
</script>

<template>
  <label
    v-for="control in controls"
    :key="control.level.id"
    class="field"
  >
    <span>{{ control.level.label }}<abbr
      v-if="control.level.required"
      class="required"
      title="Needed before this note can be lifted"
    >*</abbr></span>
    <select
      :value="control.value"
      :data-level="control.level.id"
      :data-testid="`level-${control.level.source}`"
      @change="onChoose(control.level.id, ($event.target as HTMLSelectElement).value)"
    >
      <option value="">
        Undecided
      </option>
      <option
        v-for="option in control.inside"
        :key="option.value"
        :value="option.value"
      >
        {{ option.value }}
      </option>
      <optgroup
        v-if="control.outside.length"
        :label="`Outside ${areaName}`"
        data-outside-area
      >
        <option
          v-for="option in control.outside"
          :key="option.value"
          :value="option.value"
        >
          {{ option.value }}
        </option>
      </optgroup>
    </select>
  </label>
</template>

<style scoped>
.field { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
.field span { color: var(--muted); }
.field select {
  flex: 1; padding: 4px 6px; border: 1px solid var(--border-strong); border-radius: 5px; font-size: 12px; }
.required { color: var(--danger-strong); text-decoration: none; margin-left: 2px; }
</style>
