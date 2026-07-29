<script setup lang="ts">
/**
 * Query parameters panel: user-supplied inputs a viewpoint prompts for at execution time
 * (typed, optionally defaulted). Referenced elsewhere in the query via a `ValueRef` of
 * kind `parameter` — this panel only declares them.
 */
import { inject, ref } from 'vue'
import type { CriteriaCatalog } from '../../domain'
import type { ParameterValueType, QueryParameterNode } from '../../domain/viewpointBindings'
import { HIGHLIGHTED_NODE_ID_KEY } from './CriteriaTreeBuilder.helpers'
import { addParameter, removeParameterAt, updateParameterAt } from './QueryParametersPanel.helpers'

const props = defineProps<{
  modelValue: readonly QueryParameterNode[]
  catalog: CriteriaCatalog
}>()
const emit = defineEmits<{ 'update:modelValue': [value: QueryParameterNode[]] }>()

const highlightedNodeId = inject(HIGHLIGHTED_NODE_ID_KEY, ref(null))

const patch = (index: number, fields: Partial<QueryParameterNode>) =>
  emit('update:modelValue', updateParameterAt(props.modelValue, index, fields))
const remove = (index: number) => emit('update:modelValue', removeParameterAt(props.modelValue, index))
const add = () => emit('update:modelValue', addParameter(props.modelValue))
</script>

<template>
  <div class="panel">
    <h3>Parameters</h3>
    <p
      v-if="modelValue.length === 0"
      class="empty-state"
    >
      No parameters declared. A parameter prompts the user for a value at execution time,
      referenceable elsewhere in this query.
    </p>
    <div
      v-for="(parameter, index) in modelValue"
      :key="parameter.id"
      class="param-row"
      :class="{ highlighted: highlightedNodeId === parameter.id }"
    >
      <input
        class="inp name"
        type="text"
        placeholder="parameter name"
        :value="parameter.name"
        @input="patch(index, { name: ($event.target as HTMLInputElement).value })"
      >
      <select
        class="inp"
        :value="parameter.valueType"
        @change="patch(index, { valueType: ($event.target as HTMLSelectElement).value as ParameterValueType })"
      >
        <option
          v-for="type in catalog.parameters.types"
          :key="type"
          :value="type"
        >
          {{ type }}
        </option>
      </select>
      <label>
        <input
          type="checkbox"
          :checked="parameter.required"
          @change="patch(index, { required: ($event.target as HTMLInputElement).checked })"
        > required
      </label>
      <input
        class="inp"
        type="text"
        placeholder="default (optional)"
        :value="parameter.default"
        @input="patch(index, { default: ($event.target as HTMLInputElement).value })"
      >
      <input
        class="inp description"
        type="text"
        placeholder="description shown when prompting"
        :value="parameter.description"
        @input="patch(index, { description: ($event.target as HTMLInputElement).value })"
      >
      <button
        type="button"
        class="icon-btn"
        @click="remove(index)"
      >
        ✕
      </button>
    </div>
    <button
      type="button"
      class="add-btn"
      @click="add"
    >
      + Add parameter
    </button>
  </div>
</template>

<style scoped>
.panel { margin: 16px 0; }
.empty-state { font-size: 12.5px; color: #6b7280; background: #f9fafb; border: 1px dashed #d1d5db; border-radius: 8px; padding: 10px 12px; }
.param-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; border: 1px solid #d1d5db; border-radius: 8px; padding: 8px 10px; margin: 6px 0; font-size: 12.5px; }
.param-row.highlighted { outline: 2px solid #dc2626; outline-offset: 2px; }
.inp { font-size: 12.5px; padding: 4px 8px; border-radius: 6px; border: 1px solid #d1d5db; }
.inp.name { min-width: 140px; font-weight: 600; }
.inp.description { flex: 1; min-width: 160px; }
.icon-btn { appearance: none; border: none; background: none; color: #9ca3af; cursor: pointer; font-size: 15px; margin-left: auto; }
.icon-btn:hover { color: #991b1b; }
.add-btn { appearance: none; border: 1px dashed #d1d5db; background: #fff; color: #6b7280; border-radius: 7px; padding: 5px 10px; font-size: 12px; font-weight: 600; cursor: pointer; }
.add-btn:hover { border-color: #6366f1; color: #4338ca; }
</style>
