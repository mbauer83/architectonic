<script setup lang="ts">
/**
 * The preview's checklist of entities a model-backed diagram derived rather than the author
 * placing them. Which rows may be unchecked, and which are already out, is decided in
 * `DerivedEntityChecklist.helpers` — this file is the markup for that decision.
 */
import { computed } from 'vue'
import type { DerivedEntity } from '../../domain/schemas/diagrams'
import { derivedEntityRows, excludedRowCount } from './DerivedEntityChecklist.helpers'

const props = defineProps<{
  derived: readonly DerivedEntity[]
  excludedIds: ReadonlySet<string>
}>()
const emit = defineEmits<{ toggle: [entityId: string] }>()

const rows = computed(() => derivedEntityRows(props.derived, props.excludedIds))
const excludedCount = computed(() => excludedRowCount(rows.value))
</script>

<template>
  <div
    v-if="derived.length === 0"
    class="derived-empty"
  >
    No external connections found — consider a C4 Container diagram instead.
  </div>
  <div
    v-else
    class="derived-list"
  >
    <div class="derived-hdr">
      {{ derived.length }} entities auto-derived
      <span
        v-if="excludedCount"
        class="derived-excluded-badge"
      >{{ excludedCount }} excluded</span>
      — uncheck to exclude, then re-preview:
    </div>
    <label
      v-for="row in rows"
      :key="row.id"
      class="derived-item"
      :class="{ 'derived-item-fixed': row.fixed }"
      :title="row.note"
    >
      <input
        type="checkbox"
        :checked="row.included"
        :disabled="row.fixed"
        @change="emit('toggle', row.id)"
      >
      <span class="derived-name">{{ row.name }}</span>
      <span class="derived-type">{{ row.itemType }}</span>
      <span
        v-if="row.fixed"
        class="derived-scope-tag"
      >scope</span>
    </label>
  </div>
</template>

<style scoped>
.derived-empty {
  margin-top: 10px; font-size: 12px; color: #b45309; padding: 8px 10px;
  background: #fffbeb; border: 1px solid #fde68a; border-radius: 6px;
}
.derived-list {
  margin-top: 10px; border: 1px solid #e5e7eb; border-radius: 6px;
  padding: 8px 10px; background: #f9fafb;
}
.derived-hdr { font-size: 11px; font-weight: 600; color: #374151; margin-bottom: 6px; }
.derived-excluded-badge {
  background: #fee2e2; color: #b91c1c; border-radius: 3px;
  padding: 1px 5px; font-size: 10px; margin-left: 4px;
}
.derived-item {
  display: flex; align-items: center; gap: 6px; padding: 3px 0; cursor: pointer; font-size: 12px;
}
.derived-item input[type=checkbox] { cursor: pointer; }
.derived-item-fixed { cursor: default; }
.derived-item-fixed input[type=checkbox] { cursor: default; }
.derived-name { color: #1e293b; font-weight: 500; }
.derived-type { color: #9ca3af; font-size: 11px; }
.derived-scope-tag { background: #e0e7ff; color: #3730a3; border-radius: 3px; padding: 1px 5px; font-size: 10px; }
</style>
