<script setup lang="ts">
import { artifactKindLabel, type PromotionArtifact } from '../composables/promotionShared'

defineProps<{
  title: string
  artifacts: PromotionArtifact[]
}>()

const emit = defineEmits<{
  remove: [artifactId: string]
}>()
</script>

<template>
  <div class="form-row">
    <label class="section-title">{{ title }} ({{ artifacts.length }})</label>
    <div class="artifact-list">
      <div
        v-for="artifact in artifacts"
        :key="artifact.artifact_id"
        class="artifact-row"
      >
        <div class="artifact-row__main">
          <span class="artifact-row__name">{{ artifact.name }}</span>
          <span class="artifact-kind-badge">{{ artifactKindLabel(artifact.record_type) }}</span>
          <span class="artifact-row__id mono">{{ artifact.artifact_id }}</span>
        </div>
        <button
          class="artifact-row__remove"
          type="button"
          @click="emit('remove', artifact.artifact_id)"
        >
          Remove
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.form-row { margin-bottom: 16px; }
.section-title { font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: var(--text-2); margin-bottom: 8px; display: block; }
.artifact-list { display: flex; flex-direction: column; gap: 8px; }
.artifact-row {
  display: flex; justify-content: space-between; align-items: center; gap: 12px;
  border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px;
}
.artifact-row__main { display: flex; align-items: center; gap: 8px; min-width: 0; flex-wrap: wrap; }
.artifact-row__name { font-weight: 500; color: var(--text); }
.artifact-kind-badge {
  display: inline-flex; align-items: center; border-radius: 999px; padding: 2px 8px;
  background: var(--border); color: var(--text-2); font-size: 11px; font-weight: 600;
}
.artifact-row__id { font-size: 11px; color: var(--faint); }
.artifact-row__remove {
  padding: 5px 10px; border-radius: 6px; border: 1px solid var(--danger-border); background: var(--danger-soft);
  color: var(--danger-strong); font-size: 12px; cursor: pointer; white-space: nowrap;
}
.artifact-row__remove:hover { background: var(--danger-soft); }
.mono { font-family: monospace; font-size: 12px; }
</style>
