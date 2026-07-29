<script setup lang="ts">
/**
 * Matrix axis editor: grouped (`row_by`/`column_by`, one population split by a key) and
 * criteria (`row_criteria`/`column_criteria`, two independent populations) are mutually
 * exclusive — picking one clears the other's fields, not just at save time.
 */
import { computed } from 'vue'
import type { CriteriaCatalog } from '../../domain'
import { GROUP_BY_DIMENSIONS, matrixAxisMode } from '../../domain/viewpointPresentation'
import type { MatrixAxisMode, PresentationNode } from '../../domain/viewpointPresentation'
import { mkGroup } from '../../domain/viewpointCriteria'
import CriteriaTreeBuilder from './CriteriaTreeBuilder.vue'

const props = defineProps<{
  modelValue: PresentationNode
  catalog: CriteriaCatalog
}>()
const emit = defineEmits<{ 'update:modelValue': [value: PresentationNode] }>()

const groupByOptions = computed(() => [...GROUP_BY_DIMENSIONS, ...Object.keys(props.catalog.entity_attribute_types)])
const mode = computed(() => matrixAxisMode(props.modelValue))

const setMode = (next: MatrixAxisMode) => {
  if (next === 'grouped') {
    emit('update:modelValue', {
      ...props.modelValue, rowCriteria: null, columnCriteria: null,
      rowBy: props.modelValue.rowBy ?? groupByOptions.value[0], columnBy: props.modelValue.columnBy ?? groupByOptions.value[0],
    })
  } else {
    emit('update:modelValue', {
      ...props.modelValue, rowBy: null, columnBy: null,
      rowCriteria: props.modelValue.rowCriteria ?? mkGroup('entity'),
      columnCriteria: props.modelValue.columnCriteria ?? mkGroup('entity'),
    })
  }
}
</script>

<template>
  <div class="matrix-axes">
    <div class="mode-toggle">
      <button
        type="button"
        :class="{ sel: mode === 'grouped' }"
        @click="setMode('grouped')"
      >
        Grouped axes
      </button>
      <button
        type="button"
        :class="{ sel: mode === 'criteria' }"
        @click="setMode('criteria')"
      >
        Criteria axes
      </button>
    </div>

    <div
      v-if="mode === 'grouped'"
      class="grid2"
    >
      <label class="field">
        row_by
        <select
          class="inp"
          :value="modelValue.rowBy ?? ''"
          @change="emit('update:modelValue', { ...modelValue, rowBy: ($event.target as HTMLSelectElement).value })"
        >
          <option
            v-for="option in groupByOptions"
            :key="option"
            :value="option"
          >
            {{ option }}
          </option>
        </select>
      </label>
      <label class="field">
        column_by
        <select
          class="inp"
          :value="modelValue.columnBy ?? ''"
          @change="emit('update:modelValue', { ...modelValue, columnBy: ($event.target as HTMLSelectElement).value })"
        >
          <option
            v-for="option in groupByOptions"
            :key="option"
            :value="option"
          >
            {{ option }}
          </option>
        </select>
      </label>
    </div>

    <div
      v-else-if="mode === 'criteria'"
      class="grid2"
    >
      <div>
        <div class="builder-title">
          row_criteria
        </div>
        <CriteriaTreeBuilder
          v-if="modelValue.rowCriteria"
          :model-value="modelValue.rowCriteria"
          group-kind="entity"
          :catalog="catalog"
          is-root
          @update:model-value="emit('update:modelValue', { ...modelValue, rowCriteria: $event })"
        />
      </div>
      <div>
        <div class="builder-title">
          column_criteria
        </div>
        <CriteriaTreeBuilder
          v-if="modelValue.columnCriteria"
          :model-value="modelValue.columnCriteria"
          group-kind="entity"
          :catalog="catalog"
          is-root
          @update:model-value="emit('update:modelValue', { ...modelValue, columnCriteria: $event })"
        />
      </div>
      <p class="note">
        The base query's entity_criteria is left at match-everything so each axis carries
        its own full selection — a fully disjoint matrix (e.g. requirements × components).
      </p>
    </div>
  </div>
</template>

<style scoped>
.mode-toggle { display: inline-flex; border: 1px solid #d1d5db; border-radius: 99px; overflow: hidden; margin-bottom: 12px; }
.mode-toggle button { appearance: none; border: none; background: #fff; color: #6b7280; font-size: 12px; font-weight: 700; padding: 5px 14px; cursor: pointer; }
.mode-toggle button.sel { background: #6366f1; color: #fff; }
.grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.field { display: flex; flex-direction: column; gap: 4px; font-size: 12px; font-weight: 600; color: #6b7280; }
.inp { padding: 5px 8px; border-radius: 6px; border: 1px solid #d1d5db; font-size: 13px; font-family: inherit; }
.builder-title { font-size: 11px; font-weight: 700; color: #9ca3af; text-transform: uppercase; letter-spacing: .05em; margin-bottom: 6px; }
.note { grid-column: 1 / -1; font-size: 12px; color: #6b7280; }
</style>
