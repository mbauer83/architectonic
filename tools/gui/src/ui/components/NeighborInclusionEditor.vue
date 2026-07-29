<script setup lang="ts">
/**
 * "Neighbor inclusions" editor for the query tab: a list of population-widening rules,
 * each a direction + traversal (direct/derived, with include-potential and max-hops for
 * derived) plus optional connection/neighbor criteria slots. Owns only list add/remove/
 * patch; the query tab v-models the `includeConnected` array onto this.
 */
import type { CriteriaCatalog } from '../../domain'
import { mkNeighborInclusion } from '../../domain/viewpointCriteria'
import type { NeighborInclusionNode } from '../../domain/viewpointCriteria'
import OptionalCriteriaSlot from './OptionalCriteriaSlot.vue'

const props = withDefaults(defineProps<{
  modelValue: readonly NeighborInclusionNode[]
  catalog: CriteriaCatalog
  bindingNames?: readonly string[]
  parameterNames?: readonly string[]
}>(), { bindingNames: () => [], parameterNames: () => [] })
const emit = defineEmits<{ 'update:modelValue': [value: NeighborInclusionNode[]] }>()

const add = () => emit('update:modelValue', [...props.modelValue, mkNeighborInclusion()])
const remove = (index: number) => emit('update:modelValue', props.modelValue.filter((_, i) => i !== index))
const patch = (index: number, changes: Partial<NeighborInclusionNode>) => {
  const next = [...props.modelValue]
  next[index] = { ...next[index], ...changes }
  emit('update:modelValue', next)
}
</script>

<template>
  <div>
    <h3>Neighbor inclusions (widen the population)</h3>
    <div
      v-for="(inclusion, index) in modelValue"
      :key="inclusion.id"
      class="inclusion"
    >
      <select
        class="inp direction-select"
        :value="inclusion.direction"
        @change="patch(index, { direction: ($event.target as HTMLSelectElement).value as NeighborInclusionNode['direction'] })"
      >
        <option value="either">
          either direction
        </option>
        <option value="outgoing">
          outgoing — connections FROM the selected entities
        </option>
        <option value="incoming">
          incoming — connections TO the selected entities
        </option>
      </select>
      <select
        class="inp traversal-select"
        :value="inclusion.traversal"
        @change="patch(index, { traversal: ($event.target as HTMLSelectElement).value as NeighborInclusionNode['traversal'] })"
      >
        <option value="direct">
          direct — a single modeled connection only
        </option>
        <option value="derived">
          derived — indirect, composed across intermediate elements
        </option>
      </select>
      <template v-if="inclusion.traversal === 'derived'">
        <label class="check">
          <input
            class="include-potential-checkbox"
            :checked="inclusion.includePotential"
            type="checkbox"
            @change="patch(index, { includePotential: ($event.target as HTMLInputElement).checked })"
          > include potential (lower-confidence) relationships
        </label>
        <label class="num-field">
          max hops
          <input
            :value="inclusion.maxHops ?? ''"
            type="number"
            min="2"
            placeholder="default"
            class="inp hops-input"
            @change="patch(index, { maxHops: ($event.target as HTMLInputElement).value ? Number(($event.target as HTMLInputElement).value) : null })"
          >
        </label>
      </template>
      <button
        type="button"
        class="btn btn--danger"
        @click="remove(index)"
      >
        ✕ remove
      </button>
      <OptionalCriteriaSlot
        :model-value="inclusion.connectionCriteria"
        group-kind="connection"
        :catalog="catalog"
        :depth="0"
        :binding-names="bindingNames"
        :parameter-names="parameterNames"
        field-label="connection_criteria"
        unrestricted-label="any connection"
        @update:model-value="patch(index, { connectionCriteria: $event })"
      />
      <OptionalCriteriaSlot
        :model-value="inclusion.neighborCriteria"
        group-kind="entity"
        :catalog="catalog"
        :depth="0"
        :binding-names="bindingNames"
        :parameter-names="parameterNames"
        field-label="neighbor_criteria"
        unrestricted-label="any entity"
        @update:model-value="patch(index, { neighborCriteria: $event })"
      />
    </div>
    <button
      type="button"
      class="add-btn"
      @click="add"
    >
      + Add neighbor inclusion
    </button>
  </div>
</template>

<style scoped>
.inclusion { display: flex; flex-direction: column; align-items: flex-start; gap: 8px; border: 1px solid #d1d5db; border-radius: 8px; padding: 10px; margin: 8px 0; }
.inclusion > * { max-width: 100%; }
.inp { padding: 5px 8px; border-radius: 6px; border: 1px solid #d1d5db; font-size: 12.5px; font-family: inherit; background: #fff; box-sizing: border-box; }
select.inp { cursor: pointer; max-width: 100%; }
.check { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; color: #374151; cursor: pointer; }
.check input { margin: 0; cursor: pointer; }
.num-field { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; color: #6b7280; font-weight: 600; }
.hops-input { width: 72px; }
.btn { appearance: none; border: 1px solid #d1d5db; background: #fff; color: #374151; border-radius: 6px; padding: 5px 12px; font-size: 12.5px; font-weight: 600; cursor: pointer; }
.btn--danger:hover { border-color: #dc2626; color: #b91c1c; background: #fef2f2; }
.add-btn { appearance: none; border: 1px dashed #d1d5db; background: #fff; color: #6b7280; border-radius: 7px; padding: 5px 10px; font-size: 12px; font-weight: 600; cursor: pointer; margin-top: 8px; }
.add-btn:hover { border-color: #6366f1; color: #4338ca; }
</style>
