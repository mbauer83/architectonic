<script setup lang="ts">
/**
 * Remove-connection confirmation modal: checks diagram references before confirming (a
 * removed connection referenced by a diagram would dangle) and shows them as a warning.
 * Fully self-contained — injects the model service, owns its own query/mutation state; the
 * parent calls the exposed `requestRemove(connection)` and listens for `removed`.
 */
import { computed, inject, ref } from 'vue'
import { Exit } from 'effect'
import { modelServiceKey } from '../keys'
import type { ConnectionRecord, DiagramRefs, WriteResult } from '../../domain'
import type { RepoError } from '../../ports/ModelRepository'
import { useQuery } from '../composables/useQuery'
import { useMutation } from '../composables/useMutation'

const props = defineProps<{ adminMode?: boolean }>()
const emit = defineEmits<{ removed: [] }>()

const svc = inject(modelServiceKey)!

const removingConn = ref<ConnectionRecord | null>(null)
const diagramRefsQuery = useQuery<DiagramRefs, RepoError>()
const removeMutation = useMutation<WriteResult, RepoError>()

const removeError = computed(() =>
  removeMutation.result.value?.wrote === false
    ? (removeMutation.result.value.content ?? 'Verification failed')
    : removeMutation.errorMessage.value,
)

const requestRemove = (c: ConnectionRecord) => {
  removingConn.value = c
  removeMutation.reset()
  diagramRefsQuery.run(svc.getDiagramRefs(c.source, c.target))
}
defineExpose({ requestRemove })

const cancel = () => {
  removingConn.value = null
  diagramRefsQuery.reset()
}

const confirmRemove = () => {
  if (!removingConn.value) return
  const c = removingConn.value
  const removeFn = props.adminMode ? svc.adminRemoveConnection : svc.removeConnection
  void removeMutation.run(removeFn({
    source_entity: c.source,
    connection_type: c.conn_type,
    target_entity: c.target,
    dry_run: false,
  })).then((exit) => Exit.match(exit, {
    onSuccess: (r) => { if (r.wrote) { removingConn.value = null; emit('removed') } },
    onFailure: () => {},
  }))
}
</script>

<template>
  <div
    v-if="removingConn"
    class="modal-overlay"
    @click.self="cancel"
  >
    <div class="modal">
      <h3 class="modal-title">
        Remove connection?
      </h3>
      <p class="modal-desc">
        <strong>{{ removingConn.conn_type.replace('archimate-', '') }}</strong>
        {{ removingConn.source }} → {{ removingConn.target }}
      </p>
      <div
        v-if="diagramRefsQuery.loading.value"
        class="state-msg"
      >
        Checking diagram references...
      </div>
      <template v-else-if="(diagramRefsQuery.data.value ?? []).length">
        <p class="modal-warn">
          This connection is referenced in {{ (diagramRefsQuery.data.value ?? []).length }} diagram(s):
        </p>
        <ul class="diagram-ref-list">
          <li
            v-for="d in (diagramRefsQuery.data.value ?? [])"
            :key="d.artifact_id"
          >
            {{ d.name }}
          </li>
        </ul>
        <p class="modal-warn">
          Those diagram references will become dangling.
        </p>
      </template>
      <div
        v-if="removeError"
        class="state-msg state-msg--error"
      >
        {{ removeError }}
      </div>
      <div class="modal-actions">
        <button
          class="modal-btn modal-btn--cancel"
          @click="cancel"
        >
          Cancel
        </button>
        <button
          class="modal-btn modal-btn--danger"
          :disabled="removeMutation.running.value || diagramRefsQuery.loading.value"
          @click="confirmRemove"
        >
          Remove
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.state-msg { color: #6b7280; padding: 4px 0; font-size: 13px; }
.state-msg--error { color: #dc2626; }
.modal-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,.4); z-index: 100;
  display: flex; align-items: center; justify-content: center;
}
.modal {
  background: white; border-radius: 10px; padding: 24px; max-width: 480px;
  width: 90%; box-shadow: 0 8px 24px rgba(0,0,0,.2);
}
.modal-title { font-size: 16px; font-weight: 600; margin-bottom: 8px; }
.modal-desc { font-size: 13px; color: #374151; margin-bottom: 12px; word-break: break-all; }
.modal-warn { font-size: 13px; color: #b45309; margin-bottom: 8px; }
.diagram-ref-list { list-style: disc; padding-left: 20px; font-size: 13px; margin-bottom: 12px; }
.modal-actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 16px; }
.modal-btn {
  padding: 8px 16px; border-radius: 6px; font-size: 13px; font-weight: 500;
  cursor: pointer; border: none;
}
.modal-btn--cancel { background: #f3f4f6; color: #374151; }
.modal-btn--cancel:hover { background: #e5e7eb; }
.modal-btn--danger { background: #dc2626; color: white; }
.modal-btn--danger:hover:not(:disabled) { background: #b91c1c; }
.modal-btn--danger:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
