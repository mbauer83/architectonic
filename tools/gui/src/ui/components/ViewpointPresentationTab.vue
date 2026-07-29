<script setup lang="ts">
/**
 * "Presentation" tab of the viewpoint definition editor: representation choice, table
 * columns, matrix axes, exploration/diagram grouping, and style rules. Standard
 * modelValue/update:modelValue two-way binding, same convention MatrixAxesEditor and
 * StyleRuleEditor already use for this exact node — the parent v-models this onto its own
 * `draft.presentation`.
 */
import type { CriteriaCatalog } from '../../domain'
import {
  EXPLORATION_LAYOUTS, GROUP_BY_DIMENSIONS, layoutOption, mkColumn, mkPresentation, withLayoutOption,
} from '../../domain/viewpointPresentation'
import type {
  ColumnSpecNode, ExplorationLayout, PresentationNode, Representation,
} from '../../domain/viewpointPresentation'
import StyleRuleEditor from './StyleRuleEditor.vue'
import MatrixAxesEditor from './MatrixAxesEditor.vue'
import TargetPopulationEditor from './TargetPopulationEditor.vue'

const props = defineProps<{
  modelValue: PresentationNode | null
  catalog: CriteriaCatalog
  /** Derived-attribute names the Query tab declares — offered as `derived.<name>`
   * scale-attribute options so authored references can only point at real ones. */
  declaredDerivedNames?: readonly string[]
}>()
const emit = defineEmits<{ 'update:modelValue': [value: PresentationNode | null] }>()

const REPRESENTATIONS: Representation[] = ['exploration', 'table', 'matrix', 'diagram']

const LAYOUT_LABELS: Record<ExplorationLayout, string> = {
  clusters: 'Clusters', radial: 'Radial (by distance from anchor)', force: 'Force',
}

const emitUpdate = (patch: Partial<PresentationNode>) => {
  if (!props.modelValue) return
  emit('update:modelValue', { ...props.modelValue, ...patch })
}

const addPresentation = (representation: Representation) => emit('update:modelValue', mkPresentation(representation))
const removePresentation = () => emit('update:modelValue', null)
const changeRepresentation = (representation: Representation) => emit('update:modelValue', mkPresentation(representation))
const addColumn = () => emitUpdate({ columns: [...(props.modelValue?.columns ?? []), mkColumn()] })
const removeColumn = (index: number) => {
  if (!props.modelValue?.columns) return
  emitUpdate({ columns: props.modelValue.columns.filter((_, i) => i !== index) })
}
const updateColumn = (index: number, column: ColumnSpecNode) => {
  if (!props.modelValue?.columns) return
  const columns = [...props.modelValue.columns]
  columns[index] = column
  emitUpdate({ columns })
}
const onLayoutChange = (raw: string) => {
  if (!props.modelValue) return
  const layout = EXPLORATION_LAYOUTS.find((candidate) => candidate === raw) ?? null
  emitUpdate({ displayOptions: withLayoutOption(props.modelValue.displayOptions, layout) })
}
</script>

<template>
  <div>
    <div v-if="modelValue === null">
      <p class="empty-hint">
        No presentation — this definition is query-only (execution result has no fixed display).
      </p>
      <label class="field">
        add presentation
        <select
          class="inp"
          @change="addPresentation(($event.target as HTMLSelectElement).value as Representation)"
        >
          <option value="" />
          <option
            v-for="r in REPRESENTATIONS"
            :key="r"
            :value="r"
          >
            {{ r }}
          </option>
        </select>
      </label>
    </div>
    <div v-else>
      <div class="representation-field">
        <label
          class="field-label"
          for="vp-representation"
        >representation</label>
        <div class="representation-row">
          <select
            id="vp-representation"
            class="inp"
            :value="modelValue.representation"
            @change="changeRepresentation(($event.target as HTMLSelectElement).value as Representation)"
          >
            <option
              v-for="r in REPRESENTATIONS"
              :key="r"
              :value="r"
            >
              {{ r }}
            </option>
          </select>
          <button
            type="button"
            class="btn btn--danger"
            @click="removePresentation"
          >
            Remove presentation
          </button>
        </div>
      </div>

      <TargetPopulationEditor
        :model-value="modelValue.targetTypes"
        :entity-types="catalog.entity_types"
        @update:model-value="emitUpdate({ targetTypes: $event })"
      />

      <div v-if="modelValue.representation === 'table'">
        <h3>Columns</h3>
        <div
          v-for="(column, index) in modelValue.columns ?? []"
          :key="column.id"
          class="column-row"
        >
          <input
            :value="column.label"
            class="inp"
            placeholder="label"
            @input="updateColumn(index, { ...column, label: ($event.target as HTMLInputElement).value })"
          >
          <input
            :value="column.source"
            class="inp"
            placeholder="source (attribute path)"
            @input="updateColumn(index, { ...column, source: ($event.target as HTMLInputElement).value })"
          >
          <button
            type="button"
            class="icon-btn"
            @click="removeColumn(index)"
          >
            ✕
          </button>
        </div>
        <button
          type="button"
          class="add-btn"
          @click="addColumn"
        >
          + Add column
        </button>
      </div>

      <div v-if="modelValue.representation === 'matrix'">
        <MatrixAxesEditor
          :model-value="modelValue"
          :catalog="catalog"
          @update:model-value="emit('update:modelValue', $event)"
        />
      </div>

      <div v-if="modelValue.representation === 'exploration'">
        <label class="field">
          layout
          <select
            class="inp"
            :value="layoutOption(modelValue.displayOptions) ?? ''"
            @change="onLayoutChange(($event.target as HTMLSelectElement).value)"
          >
            <option value="">
              Auto
            </option>
            <option
              v-for="layout in EXPLORATION_LAYOUTS"
              :key="layout"
              :value="layout"
            >
              {{ LAYOUT_LABELS[layout] }}
            </option>
          </select>
        </label>
      </div>

      <div v-if="modelValue.representation === 'exploration' || modelValue.representation === 'diagram'">
        <label class="field">
          group_by
          <select
            class="inp"
            :value="modelValue.groupBy ?? ''"
            @change="emitUpdate({ groupBy: ($event.target as HTMLSelectElement).value || null })"
          >
            <option value="" />
            <option
              v-for="d in [...GROUP_BY_DIMENSIONS, ...Object.keys(catalog.entity_attribute_types)]"
              :key="d"
              :value="d"
            >
              {{ d }}
            </option>
          </select>
        </label>
        <label
          class="field"
          title="Node count above which the result opens as group super-nodes instead of a flat graph (empty = deployment default, 100)"
        >
          legibility_budget
          <input
            class="inp budget-inp"
            type="number"
            min="1"
            placeholder="100 (default)"
            :value="modelValue.legibilityBudget ?? ''"
            @input="emitUpdate({ legibilityBudget: ($event.target as HTMLInputElement).value === '' ? null : Number(($event.target as HTMLInputElement).value) })"
          >
        </label>
        <label
          class="field"
          title="How an over-budget result is aggregated into super-nodes"
        >
          aggregate_by
          <select
            class="inp"
            :value="modelValue.aggregateBy ?? ''"
            @change="emitUpdate({ aggregateBy: ($event.target as HTMLSelectElement).value || null })"
          >
            <option value="">
              auto (group_by, else group)
            </option>
            <option value="group">
              group
            </option>
            <option value="domain">
              domain
            </option>
            <option value="type">
              type
            </option>
          </select>
        </label>
      </div>

      <h3>Style rules</h3>
      <StyleRuleEditor
        :model-value="modelValue"
        :catalog="catalog"
        :declared-derived-names="props.declaredDerivedNames ?? []"
        @update:model-value="emit('update:modelValue', $event)"
      />
    </div>
  </div>
</template>

<style scoped>
.field { display: block; margin: 8px 0; font-size: 12.5px; font-weight: 600; color: #6b7280; }
.empty-hint { font-size: 13px; color: #6b7280; background: #f9fafb; border: 1px dashed #d1d5db; border-radius: 8px; padding: 10px 12px; }
.representation-field { margin: 8px 0; }
.field-label { display: block; font-size: 12.5px; font-weight: 600; color: #6b7280; margin-bottom: 3px; }
.representation-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.representation-row .inp, .representation-row .btn { min-height: 32px; margin-top: 0; }
.inp { display: block; padding: 6px 8px; border-radius: 6px; border: 1px solid #d1d5db; font-size: 13px; font-family: inherit; background: #fff; box-sizing: border-box; margin-top: 3px; }
.budget-inp { max-width: 140px; }
select.inp { cursor: pointer; min-width: 160px; }
.column-row { display: flex; gap: 6px; margin: 4px 0; align-items: center; }
.column-row .inp { flex: 1; margin-top: 0; }
.btn { appearance: none; border: 1px solid #d1d5db; background: #fff; color: #374151; border-radius: 6px; padding: 6px 12px; font-size: 12.5px; font-weight: 600; cursor: pointer; }
.btn:hover { border-color: #6366f1; color: #4338ca; }
.btn--danger:hover { border-color: #dc2626; color: #b91c1c; background: #fef2f2; }
.icon-btn { appearance: none; border: none; background: none; color: #9ca3af; cursor: pointer; font-size: 15px; line-height: 1; padding: 2px 5px; border-radius: 5px; }
.icon-btn:hover { background: #fee2e2; color: #991b1b; }
.add-btn { appearance: none; border: 1px dashed #d1d5db; background: #fff; color: #6b7280; border-radius: 7px; padding: 5px 10px; font-size: 12px; font-weight: 600; cursor: pointer; margin-top: 8px; }
.add-btn:hover { border-color: #6366f1; color: #4338ca; }
</style>
