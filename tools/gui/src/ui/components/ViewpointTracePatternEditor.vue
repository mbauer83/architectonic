<script setup lang="ts">
/**
 * Authoring surface for a query's `trace_patterns` — the branch-complete-realization grammar
 * (`viewpointTracePattern.ts`). This is the list container: progressive disclosure (F7.13)
 * means the query tab shows nothing until a pattern is added; each pattern's own editor is
 * `ViewpointTracePatternRow.vue`. There is no separate validator — a Test run submits through
 * the loader (I-G8), so this only builds well-formed shapes. The preview renders one
 * authoritative and one diagnostic cell for a sample entity through the SAME
 * `ViewpointTraceTable` projection a real execution uses (I-G5).
 */
import { ref } from 'vue'
import type { CriteriaCatalog } from '../../domain'
import {
  type TracePatternNode,
  MAX_TRACE_PATTERNS,
  mkTracePattern,
} from '../../domain/viewpointTracePattern'
import { addPattern, removeAt, replaceAt, samplePreviewTable } from './ViewpointTracePatternEditor.helpers'
import ViewpointTracePatternRow from './ViewpointTracePatternRow.vue'
import ViewpointTraceTable from './ViewpointTraceTable.vue'

const props = defineProps<{ modelValue: readonly TracePatternNode[]; catalog: CriteriaCatalog }>()
const emit = defineEmits<{ 'update:modelValue': [value: TracePatternNode[]] }>()

const showPreview = ref(false)
const layerDomains = [...new Set(Object.values(props.catalog.entity_type_domains))].sort()

const add = () => emit('update:modelValue', addPattern(props.modelValue, mkTracePattern()))
const remove = (index: number) => emit('update:modelValue', removeAt(props.modelValue, index))
const update = (index: number, next: TracePatternNode) =>
  emit('update:modelValue', replaceAt(props.modelValue, index, next))
const otherNames = (self: TracePatternNode): string[] =>
  props.modelValue.filter((p) => p.id !== self.id && p.name.length > 0).map((p) => p.name)
</script>

<template>
  <div class="panel">
    <div class="head">
      <h3>Coverage trace patterns</h3>
      <button
        v-if="modelValue.length > 0"
        type="button"
        class="link-btn"
        @click="showPreview = !showPreview"
      >
        {{ showPreview ? 'Hide' : 'Preview cells' }}
      </button>
    </div>
    <p
      v-if="modelValue.length === 0"
      class="empty-state"
    >
      No trace patterns. A trace pattern reports <strong>branch-complete</strong> realization —
      a row passes only when every modeled branch terminates in something realized, so an
      incomplete branch is an honest gap rather than a false green. Add one to turn this
      viewpoint into a coverage table.
    </p>

    <ViewpointTraceTable
      v-if="showPreview"
      :table="samplePreviewTable()"
    />

    <ViewpointTracePatternRow
      v-for="(pattern, index) in modelValue"
      :key="pattern.id"
      :pattern="pattern"
      :catalog="catalog"
      :layer-domains="layerDomains"
      :other-names="otherNames(pattern)"
      @update="update(index, $event)"
      @remove="remove(index)"
    />

    <button
      v-if="modelValue.length < MAX_TRACE_PATTERNS"
      type="button"
      class="add-btn"
      @click="add"
    >
      + Add trace pattern
    </button>
    <p
      v-else
      class="cap-warn"
    >
      Maximum of {{ MAX_TRACE_PATTERNS }} patterns per viewpoint reached.
    </p>
  </div>
</template>

<style scoped>
.panel { margin: 16px 0; }
.head { display: flex; align-items: center; gap: 12px; }
.link-btn {
  appearance: none; border: none; background: none; color: #4338ca;
  cursor: pointer; font-size: 12px; font-weight: 600;
}
.empty-state {
  font-size: 12.5px; color: #6b7280; background: #f9fafb;
  border: 1px dashed #d1d5db; border-radius: 8px; padding: 10px 12px;
}
.add-btn {
  appearance: none; border: 1px dashed #d1d5db; background: #fff; color: #6b7280;
  border-radius: 7px; padding: 5px 10px; font-size: 12px; font-weight: 600; cursor: pointer;
}
.add-btn:hover { border-color: #6366f1; color: #4338ca; }
.cap-warn { font-size: 12px; color: #92400e; background: #fef3c7; padding: 4px 10px; border-radius: 4px; }
</style>
