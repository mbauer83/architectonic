<script setup lang="ts">
/**
 * Second-order-association editor for one connection: shows the currently associated
 * entities as removable chips, plus a search-and-add row. Fully self-contained — injects
 * the model service and owns its own busy/error state; the parent shows/hides this panel
 * via `expandedAssoc` and listens for `refresh` to reload the connection list.
 */
import { inject, ref } from 'vue'
import { Effect } from 'effect'
import { modelServiceKey } from '../keys'
import type { ConnectionRecord } from '../../domain'
import EntitySearchInput from './EntitySearchInput.vue'

const props = defineProps<{ connection: ConnectionRecord }>()
const emit = defineEmits<{ refresh: [] }>()

const svc = inject(modelServiceKey)!

const friendlyName = (id: string) => {
  const parts = id.split('.')
  return parts.length > 2 ? parts.slice(2).join(' ').replace(/-/g, ' ') : id
}

const addTarget = ref<{ id: string; name: string } | null>(null)
const busy = ref(false)
const error = ref<string | null>(null)

const onTargetSelect = (id: string, name: string) => {
  addTarget.value = { id, name }
}

const addAssociation = () => {
  const picked = addTarget.value
  if (!picked) return
  busy.value = true
  error.value = null
  const c = props.connection
  Effect.runPromise(
    svc.manageConnectionAssociations({
      source_entity: c.source, connection_type: c.conn_type, target_entity: c.target,
      add_entities: [picked.id], dry_run: false,
    }),
  ).then((r) => {
    busy.value = false
    if (r.wrote) {
      addTarget.value = null
      emit('refresh')
    } else {
      error.value = r.content ?? 'Failed'
    }
  }).catch((e) => {
    busy.value = false
    error.value = String(e)
  })
}

const removeAssociation = (entityId: string) => {
  busy.value = true
  const c = props.connection
  Effect.runPromise(
    svc.manageConnectionAssociations({
      source_entity: c.source, connection_type: c.conn_type, target_entity: c.target,
      remove_entities: [entityId], dry_run: false,
    }),
  ).then((r) => {
    busy.value = false
    if (r.wrote) emit('refresh')
  }).catch(() => {
    busy.value = false
  })
}
</script>

<template>
  <div class="assoc-panel">
    <div class="assoc-chips">
      <span
        v-for="eid in (connection.associated_entities ?? [])"
        :key="eid"
        class="assoc-chip"
      >
        <RouterLink
          :to="{ path: '/entity', query: { id: eid } }"
          class="assoc-chip-link"
        >{{ friendlyName(eid) }}</RouterLink>
        <button
          class="assoc-chip-remove"
          :disabled="busy"
          @click="removeAssociation(eid)"
        >×</button>
      </span>
      <span
        v-if="!(connection.associated_entities?.length)"
        class="assoc-empty"
      >No associations</span>
    </div>
    <div class="assoc-add-row">
      <EntitySearchInput
        placeholder="Associate entity..."
        @select="onTargetSelect"
      />
      <button
        class="assoc-add-btn"
        :disabled="!addTarget || busy"
        @click="addAssociation"
      >
        +
      </button>
    </div>
    <div
      v-if="error"
      class="state-msg state-msg--error"
    >
      {{ error }}
    </div>
  </div>
</template>

<style scoped>
.state-msg { color: #6b7280; padding: 4px 0; font-size: 13px; }
.state-msg--error { color: #dc2626; }
.assoc-panel {
  margin-left: 12px; padding: 6px 10px; background: #f0f9ff;
  border-radius: 6px; border: 1px solid #bae6fd; font-size: 12px;
}
.assoc-chips { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 6px; align-items: center; }
.assoc-chip {
  display: inline-flex; align-items: center; gap: 2px;
  background: #dbeafe; border: 1px solid #93c5fd; border-radius: 12px;
  padding: 1px 6px; font-size: 11px;
}
.assoc-chip-link { color: #1d4ed8; text-decoration: none; }
.assoc-chip-link:hover { text-decoration: underline; }
.assoc-chip-remove {
  background: none; border: none; color: #64748b; cursor: pointer;
  padding: 0 1px; font-size: 12px; line-height: 1;
}
.assoc-chip-remove:hover { color: #dc2626; }
.assoc-empty { color: #94a3b8; font-style: italic; }
.assoc-add-row { display: flex; gap: 4px; align-items: center; }
.assoc-add-btn {
  padding: 4px 8px; background: #2563eb; color: white; border: none;
  border-radius: 4px; font-size: 12px; cursor: pointer; flex-shrink: 0;
}
.assoc-add-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.assoc-add-btn:hover:not(:disabled) { background: #1d4ed8; }
</style>
