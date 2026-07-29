<script setup lang="ts">
/**
 * One declared parameter's input, shared by the execution prompt (modal) and the always-on
 * toolbar so the two never drift. Renders by cardinality first, then value type:
 *   - `many` + closed vocabulary → a checkbox group (the members are known, so no free text)
 *   - `many` + open vocabulary   → a comma/newline token field (values are live model state)
 *   - `entity-id`                → the entity picker
 *   - boolean / date / number / string → the matching native input
 * Emits the draft value (`string` for scalars, `string[]` for sets); the parent owns state.
 */
import { computed } from 'vue'

import type { EntityDisplayInfo } from '../../domain'
import type { QueryParameterNode } from '../../domain/viewpointBindings'
import type { ParameterDraftValue } from '../lib/viewpointExecutionParameters'
import EntityPickerInput from './EntityPickerInput.vue'

const props = defineProps<{ parameter: QueryParameterNode; value: ParameterDraftValue }>()
const emit = defineEmits<{ update: [value: ParameterDraftValue] }>()

const asString = computed(() => (Array.isArray(props.value) ? '' : props.value))
const members = computed<readonly string[]>(() => (typeof props.value === 'string' ? [] : props.value))
const inputId = computed(() => `vp-param-${props.parameter.name}`)

const toggleMember = (member: string, on: boolean) => {
  // Preserve the parameter's declaration order so the value is stable regardless of click order.
  const next = props.parameter.allowedValues.filter((v) => (v === member ? on : members.value.includes(v)))
  emit('update', next)
}

const setOpenTokens = (raw: string) => {
  const tokens = raw.split(/[,\n]/).map((t) => t.trim()).filter(Boolean)
  emit('update', [...new Set(tokens)])
}
</script>

<template>
  <!-- set, closed vocabulary -->
  <fieldset
    v-if="parameter.cardinality === 'many' && parameter.allowedValues.length > 0"
    class="vp-pc-set"
  >
    <label
      v-for="member in parameter.allowedValues"
      :key="member"
      class="vp-pc-check"
    >
      <input
        type="checkbox"
        :checked="members.includes(member)"
        @change="toggleMember(member, ($event.target as HTMLInputElement).checked)"
      >
      {{ member }}
    </label>
  </fieldset>

  <!-- set, open vocabulary -->
  <input
    v-else-if="parameter.cardinality === 'many'"
    :id="inputId"
    type="text"
    class="vp-pc-input"
    :placeholder="`comma-separated ${parameter.valueType} values`"
    :value="members.join(', ')"
    @input="setOpenTokens(($event.target as HTMLInputElement).value)"
  >

  <EntityPickerInput
    v-else-if="parameter.valueType === 'entity-id'"
    :placeholder="`select an entity for ${parameter.name}`"
    close-on-select
    @select="(entity: EntityDisplayInfo) => emit('update', entity.artifact_id)"
  />
  <input
    v-else-if="parameter.valueType === 'boolean'"
    :id="inputId"
    type="checkbox"
    :checked="asString === 'true'"
    @change="emit('update', ($event.target as HTMLInputElement).checked ? 'true' : 'false')"
  >
  <input
    v-else-if="parameter.valueType === 'date'"
    :id="inputId"
    type="date"
    class="vp-pc-input"
    :value="asString"
    @input="emit('update', ($event.target as HTMLInputElement).value)"
  >
  <input
    v-else-if="parameter.valueType === 'integer' || parameter.valueType === 'number'"
    :id="inputId"
    type="number"
    class="vp-pc-input"
    :step="parameter.valueType === 'integer' ? '1' : 'any'"
    :value="asString"
    @input="emit('update', ($event.target as HTMLInputElement).value)"
  >
  <input
    v-else
    :id="inputId"
    type="text"
    class="vp-pc-input"
    :value="asString"
    @input="emit('update', ($event.target as HTMLInputElement).value)"
  >
</template>

<style scoped>
.vp-pc-set { display: flex; flex-wrap: wrap; gap: 4px 14px; border: 0; margin: 0; padding: 0; }
.vp-pc-check {
  display: inline-flex; align-items: center; gap: 4px; font-size: 12.5px; font-weight: 400; color: #374151;
}
.vp-pc-input { padding: 6px 8px; border-radius: 6px; border: 1px solid #d1d5db; font-size: 13px; font-family: inherit; }
</style>
