<script setup lang="ts">
/**
 * Item-scoped derived attributes panel: for each candidate entity, enumerate incident
 * (direct) or relationship-derived connections matching criteria, then reduce — addressed
 * as `derived.<name>` wherever an attribute path is usable (conditions, label/scale
 * attributes). Reuses `OptionalCriteriaSlot`/`CriteriaTreeBuilder` for its two criteria
 * legs — no separate criteria implementation.
 */
import { inject, ref } from 'vue'
import type { CriteriaCatalog } from '../../domain'
import type { AggregateKind, DerivedAttributeNode, DerivedOfHead, DerivedTraversal } from '../../domain/viewpointBindings'
import type { IncidentDirection } from '../../domain/viewpointCriteria'
import { HIGHLIGHTED_NODE_ID_KEY, attributeOptions } from './CriteriaTreeBuilder.helpers'
import { addDerivedAttribute, ofHeadOptions, removeDerivedAttributeAt, updateDerivedAttributeAt } from './QueryDerivedAttributesPanel.helpers'
import OptionalCriteriaSlot from './OptionalCriteriaSlot.vue'

const props = defineProps<{
  modelValue: readonly DerivedAttributeNode[]
  catalog: CriteriaCatalog
  bindingNames: readonly string[]
  parameterNames: readonly string[]
}>()
const emit = defineEmits<{ 'update:modelValue': [value: DerivedAttributeNode[]] }>()

const highlightedNodeId = inject(HIGHLIGHTED_NODE_ID_KEY, ref(null))

const patch = (index: number, fields: Partial<DerivedAttributeNode>) =>
  emit('update:modelValue', updateDerivedAttributeAt(props.modelValue, index, fields))
const remove = (index: number) => emit('update:modelValue', removeDerivedAttributeAt(props.modelValue, index))
const add = () => emit('update:modelValue', addDerivedAttribute(props.modelValue))

const endpointAttributeOptions = attributeOptions('entity', props.catalog).map((o) => o.path)
const connectionAttributeOptions = attributeOptions('connection', props.catalog).map((o) => o.path)
const ofAttributeOptions = (head: DerivedOfHead) => (head === 'connection' ? connectionAttributeOptions : endpointAttributeOptions)
</script>

<template>
  <div class="panel">
    <h3>Derived attributes</h3>
    <p
      v-if="modelValue.length === 0"
      class="empty-state"
    >
      No derived attributes declared. A derived attribute computes a value per candidate
      entity from its incident (or relationship-derived) connections — addressed as
      <code>derived.&lt;name&gt;</code> wherever an attribute path is usable.
    </p>
    <div
      v-for="(attribute, index) in modelValue"
      :key="attribute.id"
      class="derived-row"
      :class="{ highlighted: highlightedNodeId === attribute.id }"
    >
      <div class="derived-head">
        <input
          class="inp name"
          type="text"
          placeholder="attribute name"
          :value="attribute.name"
          @input="patch(index, { name: ($event.target as HTMLInputElement).value })"
        >
        <select
          class="inp"
          :value="attribute.direction"
          @change="patch(index, { direction: ($event.target as HTMLSelectElement).value as IncidentDirection })"
        >
          <option value="either">
            either direction
          </option>
          <option value="outgoing">
            outgoing
          </option>
          <option value="incoming">
            incoming
          </option>
        </select>
        <select
          class="inp"
          :value="attribute.traversal"
          @change="patch(index, {
            traversal: ($event.target as HTMLSelectElement).value as DerivedTraversal,
            ofHead: attribute.ofHead === 'relationship-hops' ? 'none' : attribute.ofHead,
          })"
        >
          <option
            v-for="traversal in catalog.derived.traversal"
            :key="traversal"
            :value="traversal"
          >
            {{ traversal === 'derived' ? 'relationship-derived (bounded)' : 'direct connections' }}
          </option>
        </select>
        <label v-if="attribute.traversal === 'derived'">
          <input
            type="checkbox"
            :checked="attribute.includePotential"
            @change="patch(index, { includePotential: ($event.target as HTMLInputElement).checked })"
          > include potential (not just certain)
        </label>
        <button
          type="button"
          class="icon-btn"
          @click="remove(index)"
        >
          ✕
        </button>
      </div>

      <div class="derived-sub">
        <select
          class="inp"
          :value="attribute.reduce"
          @change="patch(index, { reduce: ($event.target as HTMLSelectElement).value as AggregateKind })"
        >
          <option
            v-for="reduce in catalog.derived.reduce"
            :key="reduce"
            :value="reduce"
          >
            {{ reduce }}
          </option>
        </select>
        <select
          class="inp"
          :value="attribute.ofHead"
          @change="patch(index, { ofHead: ($event.target as HTMLSelectElement).value as DerivedOfHead, ofAttribute: null })"
        >
          <option
            v-for="head in ofHeadOptions(attribute.traversal)"
            :key="head"
            :value="head"
          >
            {{ head === 'none' ? '(nothing — count only)' : head === 'relationship-hops' ? 'hop count' : `${head} attribute` }}
          </option>
        </select>
        <select
          v-if="attribute.ofHead === 'connection' || attribute.ofHead === 'endpoint'"
          class="inp"
          :value="attribute.ofAttribute ?? ''"
          @change="patch(index, { ofAttribute: ($event.target as HTMLSelectElement).value || null })"
        >
          <option
            v-for="path in ofAttributeOptions(attribute.ofHead)"
            :key="path"
            :value="path"
          >
            {{ path }}
          </option>
        </select>
        <input
          v-if="attribute.traversal === 'derived'"
          class="inp hops"
          type="number"
          min="1"
          placeholder="max hops (optional)"
          :value="attribute.maxHops ?? ''"
          @input="patch(index, { maxHops: ($event.target as HTMLInputElement).value ? Number(($event.target as HTMLInputElement).value) : null })"
        >
      </div>

      <OptionalCriteriaSlot
        :model-value="attribute.connectionCriteria"
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
        :model-value="attribute.endpointCriteria"
        group-kind="entity"
        :catalog="catalog"
        :depth="0"
        :binding-names="bindingNames"
        :parameter-names="parameterNames"
        field-label="endpoint_criteria"
        unrestricted-label="any entity"
        @update:model-value="patch(index, { endpointCriteria: $event })"
      />
    </div>
    <button
      type="button"
      class="add-btn"
      @click="add"
    >
      + Add derived attribute
    </button>
  </div>
</template>

<style scoped>
.panel { margin: 16px 0; }
.empty-state { font-size: 12.5px; color: #6b7280; background: #f9fafb; border: 1px dashed #d1d5db; border-radius: 8px; padding: 10px 12px; }
.derived-row { border: 1px solid #d1d5db; border-radius: 8px; padding: 10px; margin: 8px 0; }
.derived-row.highlighted { outline: 2px solid #dc2626; outline-offset: 2px; }
.derived-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 6px; font-size: 12.5px; }
.derived-sub { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 12.5px; margin: 6px 0; }
.inp { font-size: 12.5px; padding: 4px 8px; border-radius: 6px; border: 1px solid #d1d5db; }
.inp.name { min-width: 140px; font-weight: 600; }
.inp.hops { width: 140px; }
.icon-btn { appearance: none; border: none; background: none; color: #9ca3af; cursor: pointer; font-size: 15px; margin-left: auto; }
.icon-btn:hover { color: #991b1b; }
.add-btn { appearance: none; border: 1px dashed #d1d5db; background: #fff; color: #6b7280; border-radius: 7px; padding: 5px 10px; font-size: 12px; font-weight: 600; cursor: pointer; }
.add-btn:hover { border-color: #6366f1; color: #4338ca; }
</style>
