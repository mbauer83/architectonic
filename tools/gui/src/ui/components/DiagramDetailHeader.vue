<script setup lang="ts">
/** Page header for the diagram detail view: back link, title, download menu, and the
 * promote/edit/sync/delete action row. Pure display + button clicks emitted up — the sync
 * and delete flows themselves live in DiagramSyncPanel/DiagramDeletePanel.
 *
 * A diagram edited on its canvas enters edit mode in place: *Edit* emits `edit`, and while editing the
 * same place holds *Done* (`Esc`) and nothing else leaves the header — download, promote, sync and
 * delete act on the stored diagram, which is not what is on the screen. */
import type { DiagramDetail } from '../../domain'
import { EMPTY_READING_LENS, type ReadingLens } from '../../domain/readingLens'
import DiagramDownloadMenu from './DiagramDownloadMenu.vue'

withDefaults(defineProps<{
  detail: DiagramDetail
  diagramId: string
  editPath: string
  isGlobalDiagram: boolean
  adminMode: boolean
  /** The reader's ad-hoc reading, so the download exports the picture on screen rather than the
   * authored one. Defaulted, because the listing view mounts this header with no reading at all. */
  lens?: ReadingLens
  /** Edited on its canvas, on this page, rather than on the editor's own page. */
  editsOnCanvas?: boolean
  editing?: boolean
}>(), { lens: () => EMPTY_READING_LENS, editsOnCanvas: false, editing: false })
const emit = defineEmits<{ sync: []; delete: []; edit: []; done: [] }>()
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
    <button
      v-if="editing"
      type="button"
      class="done-btn"
      data-testid="diagram-done"
      @click="emit('done')"
    >
      Done <kbd>Esc</kbd>
    </button>
    <template v-else>
      <DiagramDownloadMenu
        :diagram-id="diagramId"
        :lens="lens"
      />
      <RouterLink
        v-if="!isGlobalDiagram"
        :to="{ path: '/promote', query: { diagram_id: diagramId } }"
        class="promote-btn"
      >
        ↑ Promote to Enterprise
      </RouterLink>
      <button
        v-if="editsOnCanvas"
        type="button"
        class="edit-btn"
        data-testid="diagram-edit"
        @click="emit('edit')"
      >
        Edit
      </button>
      <RouterLink
        v-else
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
    </template>
  </div>
</template>

<style scoped>
.page-hdr { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.back { font-size: 13px; color: var(--muted); } .back:hover { color: var(--text-2); text-decoration: none; }
.pg-title { font-size: 20px; font-weight: 700; flex: 1; margin: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.promote-btn {
  padding: 5px 16px; background: var(--warn-soft); border: 1px solid var(--warn-border); border-radius: 6px;
  font-size: 13px; font-weight: 500; color: var(--warn-text); text-decoration: none; flex-shrink: 0;
}
.promote-btn:hover { background: var(--warn-border); text-decoration: none; }
.edit-btn { padding: 5px 16px; background: var(--soft); border: 1px solid var(--border-strong); border-radius: 6px; font-size: 13px; font-weight: 500; color: var(--text-2); text-decoration: none; flex-shrink: 0; } .edit-btn:hover { background: var(--border); }
.edit-btn { cursor: pointer; }
.done-btn {
  padding: 5px 16px; background: var(--accent-soft); border: 1px solid var(--accent); border-radius: 6px;
  font-size: 13px; font-weight: 600; color: var(--accent-strong); cursor: pointer; flex-shrink: 0;
}
.done-btn:hover { background: var(--accent-border); }
.done-btn kbd {
  font: 10px ui-monospace, monospace; padding: 0 4px; margin-left: 4px; border: 1px solid var(--border-strong);
  border-bottom-width: 2px; border-radius: 3px; background: var(--surface); font-weight: 400;
}
.sync-btn { padding: 5px 16px; background: var(--accent-soft); border: 1px solid var(--accent-border); border-radius: 6px; font-size: 13px; font-weight: 600; color: var(--accent-strong); cursor: pointer; flex-shrink: 0; }
.sync-btn:hover { background: var(--type-soft); }
.delete-btn { padding: 5px 16px; background: var(--danger-soft); border: 1px solid var(--danger-border); border-radius: 6px; font-size: 13px; font-weight: 600; color: var(--danger-strong); cursor: pointer; flex-shrink: 0; }
.delete-btn:hover { background: var(--danger-soft); }
</style>
