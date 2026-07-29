<script setup lang="ts">
/** Page header for the diagram detail view: back link, title, download menu, and the
 * promote/edit/sync/delete action row. Pure display + button clicks emitted up — the sync
 * and delete flows themselves live in DiagramSyncPanel/DiagramDeletePanel. */
import type { DiagramDetail } from '../../domain'
import DownloadMenu from './DownloadMenu.vue'

defineProps<{
  detail: DiagramDetail
  diagramId: string
  editPath: string
  isGlobalDiagram: boolean
  adminMode: boolean
}>()
const emit = defineEmits<{ sync: []; delete: [] }>()
</script>

<template>
  <div class="page-hdr">
    <RouterLink
      to="/diagrams"
      class="back"
    >
      ← Diagrams
    </RouterLink>
    <h1 class="pg-title">
      {{ detail.name }}
    </h1>
    <DownloadMenu
      :diagram-id="diagramId"
      :diagram-name="detail.name"
    />
    <RouterLink
      v-if="!isGlobalDiagram"
      :to="{ path: '/promote', query: { diagram_id: diagramId } }"
      class="promote-btn"
    >
      ↑ Promote to Enterprise
    </RouterLink>
    <RouterLink
      :to="{ path: editPath, query: { id: diagramId } }"
      class="edit-btn"
    >
      Edit
    </RouterLink>
    <button
      v-if="!isGlobalDiagram"
      class="sync-btn"
      @click="emit('sync')"
    >
      Sync to model
    </button>
    <button
      v-if="!isGlobalDiagram || adminMode"
      class="delete-btn"
      @click="emit('delete')"
    >
      Delete{{ isGlobalDiagram && adminMode ? ' ⚠' : '' }}
    </button>
  </div>
</template>

<style scoped>
.page-hdr { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.back { font-size: 13px; color: #6b7280; } .back:hover { color: #374151; text-decoration: none; }
.pg-title { font-size: 20px; font-weight: 700; flex: 1; margin: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.promote-btn {
  padding: 5px 16px; background: #fef3c7; border: 1px solid #fde68a; border-radius: 6px;
  font-size: 13px; font-weight: 500; color: #92400e; text-decoration: none; flex-shrink: 0;
}
.promote-btn:hover { background: #fde68a; text-decoration: none; }
.edit-btn { padding: 5px 16px; background: #f3f4f6; border: 1px solid #d1d5db; border-radius: 6px; font-size: 13px; font-weight: 500; color: #374151; text-decoration: none; flex-shrink: 0; } .edit-btn:hover { background: #e5e7eb; }
.sync-btn { padding: 5px 16px; background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 6px; font-size: 13px; font-weight: 600; color: #1d4ed8; cursor: pointer; flex-shrink: 0; }
.sync-btn:hover { background: #dbeafe; }
.delete-btn { padding: 5px 16px; background: #fef2f2; border: 1px solid #fecaca; border-radius: 6px; font-size: 13px; font-weight: 600; color: #b91c1c; cursor: pointer; flex-shrink: 0; }
.delete-btn:hover { background: #fee2e2; }
</style>
