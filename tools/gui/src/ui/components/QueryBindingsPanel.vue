<script setup lang="ts">
/**
 * Named query bindings ("let") panel: each binding declares an entity or connection
 * selection (or a tuple of earlier bindings), an optional attribute projection and
 * reduction, and whether it widens the result. Reuses `CriteriaTreeBuilder` for a
 * selection binding's own criteria — no separate criteria implementation.
 */
import { computed, inject, ref } from 'vue'
import type { CriteriaCatalog } from '../../domain'
import type { AggregateKind, QueryBindingNode } from '../../domain/viewpointBindings'
import { attributeTypeTablesFromCatalog, bindingGroupKind, resultTypeStringFor } from '../../domain/viewpointBindings'
import { AGGREGATE_CHOICES, HIGHLIGHTED_NODE_ID_KEY, attributeOptions } from './CriteriaTreeBuilder.helpers'
import { addBinding, canIncludeInResult, earlierBindingNames, removeBindingAt, updateBindingAt } from './QueryBindingsPanel.helpers'
import CriteriaTreeBuilder from './CriteriaTreeBuilder.vue'

const props = defineProps<{
  modelValue: readonly QueryBindingNode[]
  catalog: CriteriaCatalog
  parameterNames: readonly string[]
}>()
const emit = defineEmits<{ 'update:modelValue': [value: QueryBindingNode[]] }>()

const highlightedNodeId = inject(HIGHLIGHTED_NODE_ID_KEY, ref(null))

const attributeTypes = computed(() => attributeTypeTablesFromCatalog(props.catalog))
const bindingNamesFor = (index: number) => earlierBindingNames(props.modelValue, index)
const allBindingNames = computed(() => props.modelValue.filter((b) => b.name.length > 0).map((b) => b.name))

const patch = (index: number, fields: Partial<QueryBindingNode>) =>
  emit('update:modelValue', updateBindingAt(props.modelValue, index, fields))
const remove = (index: number) => emit('update:modelValue', removeBindingAt(props.modelValue, index))
const add = () => emit('update:modelValue', addBinding(props.modelValue))

const projectOptions = (binding: QueryBindingNode) =>
  attributeOptions(bindingGroupKind(binding.select), props.catalog).map((o) => o.path)

const inferredType = (binding: QueryBindingNode) => resultTypeStringFor(binding, props.modelValue, attributeTypes.value)
</script>

<template>
  <div class="panel">
    <h3>Named bindings</h3>
    <p
      v-if="modelValue.length === 0"
      class="empty-state"
    >
      No bindings declared. A binding names a set of entities/connections (or a tuple of
      earlier bindings) so conditions elsewhere in this query can reference it.
    </p>
    <div
      v-for="(binding, index) in modelValue"
      :key="binding.id"
      class="binding-row"
      :class="{ highlighted: highlightedNodeId === binding.id }"
    >
      <div class="binding-head">
        <input
          class="inp name"
          type="text"
          placeholder="binding name"
          :value="binding.name"
          @input="patch(index, { name: ($event.target as HTMLInputElement).value })"
        >
        <select
          class="inp"
          :value="binding.mode"
          @change="patch(index, { mode: ($event.target as HTMLSelectElement).value as QueryBindingNode['mode'] })"
        >
          <option value="select">
            declares a selection
          </option>
          <option value="tuple">
            declares a tuple of earlier bindings
          </option>
        </select>
        <span class="inferred-type">{{ inferredType(binding) }}</span>
        <button
          type="button"
          class="icon-btn"
          @click="remove(index)"
        >
          ✕
        </button>
      </div>

      <template v-if="binding.mode === 'select'">
        <div class="binding-sub">
          <label>
            <input
              type="radio"
              name="select-kind"
              :checked="binding.select === 'entities'"
              @change="patch(index, { select: 'entities' })"
            > entity selection
          </label>
          <label>
            <input
              type="radio"
              name="select-kind"
              :checked="binding.select === 'connections'"
              @change="patch(index, { select: 'connections' })"
            > connection selection
          </label>
          <select
            class="inp"
            :value="binding.cardinality"
            @change="patch(index, { cardinality: ($event.target as HTMLSelectElement).value as QueryBindingNode['cardinality'] })"
          >
            <option value="instance">
              exactly one
            </option>
            <option value="optional">
              zero or one
            </option>
            <option value="set">
              any number
            </option>
          </select>
        </div>

        <CriteriaTreeBuilder
          :model-value="binding.criteria"
          :group-kind="bindingGroupKind(binding.select)"
          :catalog="catalog"
          :binding-names="bindingNamesFor(index)"
          :parameter-names="parameterNames"
          is-root
          @update:model-value="patch(index, { criteria: $event })"
        />

        <div class="binding-sub">
          <select
            class="inp"
            :value="binding.project ?? ''"
            @change="patch(index, { project: ($event.target as HTMLSelectElement).value || null })"
          >
            <option value="">
              (no attribute projection)
            </option>
            <option
              v-for="path in projectOptions(binding)"
              :key="path"
              :value="path"
            >
              project {{ path }}
            </option>
          </select>
          <select
            class="inp"
            :value="binding.aggregate ?? ''"
            @change="patch(index, { aggregate: (($event.target as HTMLSelectElement).value || null) as AggregateKind | null })"
          >
            <option value="">
              (no reduction)
            </option>
            <option
              v-for="choice in AGGREGATE_CHOICES"
              :key="choice"
              :value="choice"
            >
              {{ choice }}
            </option>
          </select>
          <label v-if="canIncludeInResult(binding)">
            <input
              type="checkbox"
              :checked="binding.includeInResult"
              @change="patch(index, { includeInResult: ($event.target as HTMLInputElement).checked })"
            > include these entities in the result
          </label>
        </div>
      </template>

      <div
        v-else
        class="binding-sub"
      >
        <span class="sub-label">tuple of:</span>
        <label
          v-for="name in bindingNamesFor(index)"
          :key="name"
        >
          <input
            type="checkbox"
            :checked="binding.tupleOf.includes(name)"
            @change="patch(index, {
              tupleOf: ($event.target as HTMLInputElement).checked
                ? [...binding.tupleOf, name]
                : binding.tupleOf.filter((n) => n !== name),
            })"
          > {{ name }}
        </label>
        <span
          v-if="bindingNamesFor(index).length === 0"
          class="empty-hint"
        >no earlier bindings to combine yet.</span>
      </div>
    </div>

    <button
      type="button"
      class="add-btn"
      @click="add"
    >
      + Add binding
    </button>
    <p
      v-if="allBindingNames.length === 0 && modelValue.length > 0"
      class="empty-hint"
    >
      Name every binding to make it referenceable elsewhere in this query.
    </p>
  </div>
</template>

<style scoped>
.panel { margin: 16px 0; }
.empty-state { font-size: 12.5px; color: #6b7280; background: #f9fafb; border: 1px dashed #d1d5db; border-radius: 8px; padding: 10px 12px; }
.binding-row { border: 1px solid #d1d5db; border-radius: 8px; padding: 10px; margin: 8px 0; }
.binding-row.highlighted { outline: 2px solid #dc2626; outline-offset: 2px; }
.binding-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 6px; }
.binding-sub { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; font-size: 12.5px; margin: 6px 0; }
.sub-label { font-size: 11px; color: #9ca3af; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; }
.inp { font-size: 12.5px; padding: 4px 8px; border-radius: 6px; border: 1px solid #d1d5db; }
.inp.name { min-width: 160px; font-weight: 600; }
.inferred-type { font-size: 11px; color: #4338ca; background: #eef2ff; padding: 2px 8px; border-radius: 99px; font-family: monospace; }
.icon-btn { appearance: none; border: none; background: none; color: #9ca3af; cursor: pointer; font-size: 15px; margin-left: auto; }
.icon-btn:hover { color: #991b1b; }
.empty-hint { font-size: 12px; color: #92400e; background: #fef3c7; padding: 2px 8px; border-radius: 4px; }
.add-btn { appearance: none; border: 1px dashed #d1d5db; background: #fff; color: #6b7280; border-radius: 7px; padding: 5px 10px; font-size: 12px; font-weight: 600; cursor: pointer; }
.add-btn:hover { border-color: #6366f1; color: #4338ca; }
</style>
