<script setup lang="ts">
/**
 * Sync-to-model confirmation panel for a diagram: dry-run preview (stale entity/connection
 * references that would be removed, plus warnings) before applying. Fully self-contained,
 * same shape as DiagramDeletePanel — the parent calls the exposed `requestSync()` from its
 * own "Sync to model" button and listens for `synced` to reload the diagram.
 */
import { computed, inject, ref } from 'vue'
import { Exit } from 'effect'
import { modelServiceKey } from '../keys'
import { useMutation } from '../composables/useMutation'
import type { RepoError } from '../../ports/ModelRepository'
import type { SyncDiagramToModelResult } from '../../domain'

const props = defineProps<{ diagramId: string }>()
const emit = defineEmits<{ synced: [] }>()

const svc = inject(modelServiceKey)!
const syncMutation = useMutation<SyncDiagramToModelResult, RepoError>()
const confirmSync = ref(false)
const syncPreview = ref<SyncDiagramToModelResult | null>(null)
const syncError = computed(() => {
  const r = syncMutation.result.value
  if (r && !r.wrote) return r.content ?? 'Sync failed'
  return syncMutation.errorMessage.value
})

const requestSync = () => {
  confirmSync.value = true
  syncPreview.value = null
  syncMutation.reset()
  void syncMutation.run(svc.syncDiagramToModel({ artifact_id: props.diagramId, dry_run: true }))
    .then((exit) => Exit.match(exit, {
      onSuccess: (r) => { syncPreview.value = r },
      onFailure: () => {},
    }))
}
defineExpose({ requestSync })

const cancel = () => {
  confirmSync.value = false
  syncPreview.value = null
  syncMutation.reset()
}

const executeSync = () => {
  void syncMutation.run(svc.syncDiagramToModel({ artifact_id: props.diagramId, dry_run: false }))
    .then((exit) => Exit.match(exit, {
      onSuccess: (r) => {
        if (r.wrote) {
          confirmSync.value = false
          syncPreview.value = null
          emit('synced')
        }
      },
      onFailure: () => {},
    }))
}
</script>

<template>
  <div
    v-if="confirmSync"
    class="sync-panel"
  >
    <div class="sync-title">
      Sync diagram to model
    </div>
    <div class="sync-text">
      Entities and connections no longer in the model will be removed; names will be refreshed.
    </div>
    <template v-if="syncPreview">
      <div
        v-if="syncPreview.removed_entity_ids.length || syncPreview.removed_connection_ids.length"
        class="sync-removed"
      >
        <span v-if="syncPreview.removed_entity_ids.length">
          {{ syncPreview.removed_entity_ids.length }} stale
          {{ syncPreview.removed_entity_ids.length === 1 ? 'entity' : 'entities' }} will be removed.
        </span>
        <span v-if="syncPreview.removed_connection_ids.length">
          {{ syncPreview.removed_connection_ids.length }} stale
          {{ syncPreview.removed_connection_ids.length === 1 ? 'connection' : 'connections' }} will be removed.
        </span>
      </div>
      <div
        v-else
        class="sync-uptodate"
      >
        Diagram is already up to date — no stale references found.
      </div>
      <div
        v-if="syncPreview.warnings.length"
        class="preview-warnings"
      >
        <div
          v-for="w in syncPreview.warnings"
          :key="w"
          class="preview-warn"
        >
          {{ w }}
        </div>
      </div>
    </template>
    <pre
      v-if="syncError"
      class="state err state-block"
    >{{ syncError }}</pre>
    <div class="sync-actions">
      <button
        class="toggle-btn"
        :disabled="syncMutation.running.value"
        @click="cancel"
      >
        Cancel
      </button>
      <button
        class="sync-confirm-btn"
        :disabled="syncMutation.running.value || !syncPreview"
        @click="executeSync"
      >
        {{ syncMutation.running.value ? 'Syncing…' : 'Apply sync' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.state { color: #6b7280; } .err { color: #dc2626; }
.state-block { white-space: pre-wrap; overflow-x: auto; }
.sync-panel { margin-top: 16px; padding: 16px; background: #f0f9ff; border: 1px solid #bae6fd; border-radius: 8px; }
.sync-title { font-size: 14px; font-weight: 700; color: #0c4a6e; margin-bottom: 6px; }
.sync-text { font-size: 13px; color: #0369a1; margin-bottom: 10px; }
.sync-removed { font-size: 13px; color: #b45309; background: #fffbeb; border: 1px solid #fde68a; border-radius: 6px; padding: 8px 10px; margin-bottom: 10px; display: flex; flex-direction: column; gap: 2px; }
.sync-uptodate { font-size: 13px; color: #166534; background: #f0fdf4; border: 1px solid #bbf7d0; border-radius: 6px; padding: 8px 10px; margin-bottom: 10px; }
.preview-warnings { display: flex; flex-direction: column; gap: 2px; margin-bottom: 10px; }
.preview-warn { font-size: 12px; color: #92400e; background: #fef3c7; padding: 4px 8px; border-radius: 4px; }
.sync-actions { display: flex; gap: 8px; justify-content: flex-end; }
.toggle-btn { padding: 5px 14px; border-radius: 6px; border: 1px solid #d1d5db; background: white; font-size: 13px; cursor: pointer; color: #374151; } .toggle-btn:hover { background: #f9fafb; }
.sync-confirm-btn { padding: 5px 16px; background: #2563eb; border: none; border-radius: 6px; font-size: 13px; font-weight: 600; color: white; cursor: pointer; }
.sync-confirm-btn:hover:not(:disabled) { background: #1d4ed8; }
.sync-confirm-btn:disabled { opacity: .5; cursor: not-allowed; }
</style>
