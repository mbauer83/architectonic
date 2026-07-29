<script setup lang="ts">
import type { GeneralizationSet } from './useDatatypeModel'

defineProps<{
  sets: GeneralizationSet[]
}>()
const emit = defineEmits<{
  add: []
  remove: [id: string]
  update: [id: string, patch: Partial<GeneralizationSet>]
}>()
</script>

<template>
  <div class="gs">
    <div class="gs-hdr">
      <span class="gs-title">Generalization sets</span>
      <button
        class="add-btn"
        type="button"
        title="Group dt-generalizations into a {covering, disjoint} set"
        @click="emit('add')"
      >
        + Generalization set
      </button>
    </div>
    <div
      v-if="!sets.length"
      class="gs-empty"
    >
      No generalization sets. Add one to mark a sum type's cases as complete / disjoint.
    </div>
    <div
      v-for="set in sets"
      :key="set.id"
      class="gs-row"
    >
      <input
        class="gs-name"
        type="text"
        :value="set.label ?? ''"
        placeholder="set name"
        @input="emit('update', set.id, { label: ($event.target as HTMLInputElement).value || undefined })"
      >
      <label class="gs-chk">
        <input
          type="checkbox"
          :checked="!!set.is_covering"
          @change="emit('update', set.id, { is_covering: ($event.target as HTMLInputElement).checked })"
        > complete
      </label>
      <label class="gs-chk">
        <input
          type="checkbox"
          :checked="!!set.is_disjoint"
          @change="emit('update', set.id, { is_disjoint: ($event.target as HTMLInputElement).checked })"
        > disjoint
      </label>
      <input
        class="gs-note"
        type="text"
        :value="set.note ?? ''"
        placeholder="note"
        title="Free-text note rendered on the set's constraint note"
        @input="emit('update', set.id, { note: ($event.target as HTMLInputElement).value || undefined })"
      >
      <button
        class="del-btn"
        type="button"
        title="Remove generalization set"
        @click="emit('remove', set.id)"
      >
        ×
      </button>
    </div>
  </div>
</template>

<style scoped>
.gs { display: flex; flex-direction: column; gap: 4px; }
.gs-hdr { display: flex; align-items: center; justify-content: space-between; }
.gs-title { font-size: 12px; font-weight: 600; color: #374151; }
.add-btn { font-size: 11px; padding: 2px 8px; border: 1px solid #cbd5e1; border-radius: 4px; background: #fff; cursor: pointer; }
.add-btn:hover { background: #f1f5f9; }
.gs-empty { font-size: 11px; color: #9ca3af; }
.gs-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.gs-name { width: 140px; font-size: 11px; border: 1px solid #e2e8f0; border-radius: 3px; padding: 1px 4px; }
.gs-note { flex: 1; min-width: 100px; font-size: 11px; border: 1px solid #e2e8f0; border-radius: 3px; padding: 1px 4px; }
.gs-chk { font-size: 11px; color: #6b7280; display: flex; align-items: center; gap: 3px; cursor: pointer; }
.del-btn { border: none; background: none; cursor: pointer; color: #9ca3af; font-size: 14px; padding: 0 2px; margin-left: auto; }
.del-btn:hover { color: #ef4444; }
</style>
