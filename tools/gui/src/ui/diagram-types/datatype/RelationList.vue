<script setup lang="ts">
import type { Classifier, DtConn, GeneralizationSet } from './useDatatypeModel'
import ConnRow from './ConnRow.vue'

const props = defineProps<{
  classifiers: Classifier[]
  connections: DtConn[]
  generalizationSets: GeneralizationSet[]
}>()
const emit = defineEmits<{
  addConn: [sourceId: string, targetId: string]
  removeConn: [id: string]
  updateConn: [id: string, patch: Partial<DtConn>]
}>()

const addConnDefault = () => {
  if (props.classifiers.length >= 2) {
    emit('addConn', props.classifiers[0].id, props.classifiers[1].id)
  }
}
</script>

<template>
  <div class="rl">
    <div class="rl-hdr">
      <span class="rl-title">Relations</span>
      <button
        class="add-btn"
        type="button"
        :disabled="classifiers.length < 2"
        :title="classifiers.length < 2 ? 'Add at least 2 classifiers first' : 'Add relation'"
        @click="addConnDefault()"
      >
        + Relation
      </button>
    </div>
    <div
      v-if="!connections.length"
      class="rl-empty"
    >
      No relations yet.
    </div>
    <ConnRow
      v-for="conn in connections"
      :key="conn.id"
      :conn="conn"
      :classifiers="classifiers"
      :generalization-sets="generalizationSets"
      @remove-conn="emit('removeConn', $event)"
      @update-conn="(id, patch) => emit('updateConn', id, patch)"
    />
  </div>
</template>

<style scoped>
.rl { display: flex; flex-direction: column; gap: 4px; }
.rl-hdr { display: flex; align-items: center; justify-content: space-between; }
.rl-title { font-size: 12px; font-weight: 600; color: #374151; }
.add-btn { font-size: 11px; padding: 2px 8px; border: 1px solid #cbd5e1; border-radius: 4px; background: #fff; cursor: pointer; }
.add-btn:hover:not(:disabled) { background: #f1f5f9; }
.add-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.rl-empty { font-size: 11px; color: #9ca3af; padding: 4px 0; }
</style>
