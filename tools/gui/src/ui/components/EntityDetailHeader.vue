<script setup lang="ts">
/**
 * Entity detail's top bar (back link, tier badge, graph/promote links, edit/delete/
 * cancel/preview/save actions) and header block (name/status — editable in place — plus
 * the type/domain/version/specialization meta row). `edit` (the `useEntityEditForm`
 * reactive bundle) is injected, not a prop — its fields are v-model-bound here, and a prop
 * can't legitimately be mutated (`vue/no-mutating-props`); `delete` is emitted up to
 * trigger the sibling EntityDeletePanel via the parent's template ref.
 */
import { inject } from 'vue'
import type { RouteLocationRaw } from 'vue-router'
import type { EntityDetail } from '../../domain'
import { entityEditFormKey } from '../composables/useEntityEditForm'
import ArchimateTypeGlyph from './ArchimateTypeGlyph.vue'
import { editBlockedReason } from '../lib/entityEditBlocking'

defineProps<{
  detail: EntityDetail
  entityId: string
  backTo: RouteLocationRaw
  adminMode: boolean
  isGlobalEntity: boolean
}>()
const emit = defineEmits<{ delete: [] }>()
const edit = inject(entityEditFormKey)!
</script>

<template>
  <div>
    <div class="top-bar">
      <RouterLink
        :to="backTo"
        class="back-link"
      >
        ← Browse entities
      </RouterLink>
      <div class="top-actions">
        <span
          v-if="isGlobalEntity"
          class="global-badge"
          title="From the enterprise repository"
        >Enterprise</span>
        <RouterLink
          :to="{ path: '/graph', query: { id: entityId } }"
          class="graph-btn"
        >
          Explore graph
        </RouterLink>
        <RouterLink
          v-if="!isGlobalEntity && !edit.editing"
          :to="{ path: '/promote', query: { entity_id: entityId } }"
          class="promote-btn"
          title="Promote this entity to the enterprise repository"
        >
          ↑ Promote to Enterprise
        </RouterLink>
        <button
          v-if="!edit.editing && (!isGlobalEntity || adminMode)"
          class="edit-btn"
          :class="{ 'edit-btn--admin': isGlobalEntity && adminMode }"
          :title="isGlobalEntity && adminMode ? 'Edit global entity (admin mode)' : undefined"
          @click="edit.startEdit()"
        >
          Edit{{ isGlobalEntity && adminMode ? ' ⚠' : '' }}
        </button>
        <button
          v-if="!edit.editing && (!isGlobalEntity || adminMode)"
          class="delete-btn"
          :title="isGlobalEntity && adminMode ? 'Delete global entity (admin mode)' : undefined"
          @click="emit('delete')"
        >
          Delete{{ isGlobalEntity && adminMode ? ' ⚠' : '' }}
        </button>
        <button
          v-if="edit.editing"
          class="cancel-btn"
          :disabled="edit.editBusy"
          @click="edit.cancelEdit()"
        >
          Cancel
        </button>
        <button
          v-if="edit.editing"
          class="preview-btn"
          :disabled="edit.editBusy || edit.editQuarantine.quarantined"
          :title="editBlockedReason(edit.editQuarantine.quarantined, false)"
          @click="edit.previewEdit()"
        >
          Preview
        </button>
        <button
          v-if="edit.editing"
          class="save-btn"
          :disabled="edit.editBusy || edit.editRequiredMissing || edit.editQuarantine.quarantined"
          :title="editBlockedReason(edit.editQuarantine.quarantined, edit.editRequiredMissing)"
          @click="edit.saveEdit()"
        >
          Save
        </button>
      </div>
    </div>

    <div class="entity-header">
      <div class="entity-title-row">
        <h1
          v-if="!edit.editing"
          class="entity-name"
        >
          {{ detail.name }}
        </h1>
        <input
          v-else
          v-model="edit.editName"
          class="edit-name-input"
        >
        <span
          v-if="!edit.editing"
          class="status-badge"
          :class="`status--${detail.status}`"
        >{{ detail.status }}</span>
        <select
          v-else
          v-model="edit.editStatus"
          class="edit-status-select"
        >
          <option value="draft">
            draft
          </option>
          <option value="active">
            active
          </option>
          <option value="deprecated">
            deprecated
          </option>
        </select>
      </div>
      <div class="meta-row">
        <span class="meta-type">
          <ArchimateTypeGlyph
            :type="detail.artifact_type"
            :size="16"
            class="meta-glyph"
          />
          <span class="meta-item mono">{{ detail.artifact_type }}</span>
        </span>
        <span class="sep">·</span>
        <span
          class="domain-badge"
          :class="`domain--${detail.domain}`"
        >{{ detail.domain }}</span>
        <span
          v-if="detail.subdomain"
          class="sep"
        >/ {{ detail.subdomain }}</span>
        <span class="sep">·</span>
        <span class="meta-item">v{{ detail.version }}</span>
        <template v-if="detail.specialization">
          <span class="sep">·</span>
          <span class="specialization-badge">«{{ detail.specialization }}»</span>
        </template>
      </div>
      <div class="artifact-id mono">
        {{ detail.artifact_id }}
      </div>
    </div>
  </div>
</template>

<style scoped>
.top-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.back-link { font-size: 13px; color: #6b7280; }
.back-link:hover { color: #374151; }
.top-actions { display: flex; gap: 8px; align-items: center; }

.graph-btn {
  padding: 6px 14px; border-radius: 6px; background: #1e293b; color: #f8fafc;
  font-size: 13px; font-weight: 500;
}
.graph-btn:hover { background: #334155; text-decoration: none; }

.edit-btn {
  padding: 6px 14px; border-radius: 6px; background: #f3f4f6; color: #374151;
  border: 1px solid #d1d5db; font-size: 13px; font-weight: 500; cursor: pointer;
}
.edit-btn:hover { background: #e5e7eb; }
.delete-btn {
  padding: 6px 14px; border-radius: 6px; background: #fef2f2; color: #b91c1c;
  border: 1px solid #fecaca; font-size: 13px; font-weight: 500; cursor: pointer;
}
.delete-btn:hover { background: #fee2e2; }

.promote-btn {
  padding: 6px 14px; border-radius: 6px; background: #fef3c7; color: #92400e;
  border: 1px solid #fde68a; font-size: 13px; font-weight: 500;
}
.promote-btn:hover { background: #fde68a; text-decoration: none; }

.edit-btn--admin {
  background: #7c2d12; color: #fed7aa; border-color: #ea580c;
}
.edit-btn--admin:hover { background: #9a3412; }

.global-badge {
  display: inline-block;
  background: #fef3c7; color: #92400e;
  border: 1px solid #fde68a; border-radius: 4px;
  padding: 2px 8px; font-size: 11px; font-weight: 700;
  text-transform: uppercase; letter-spacing: .05em;
}

.entity-header { margin-bottom: 20px; }
.entity-title-row { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; flex-wrap: wrap; }
.entity-name { font-size: 22px; font-weight: 700; }
.edit-name-input {
  font-size: 20px; font-weight: 600; border: 1px solid #d1d5db; border-radius: 6px;
  padding: 4px 10px; outline: none; flex: 1;
}
.edit-name-input:focus { border-color: #2563eb; }
.edit-status-select {
  padding: 3px 8px; border-radius: 6px; border: 1px solid #d1d5db; font-size: 12px; outline: none;
}

.meta-row { display: flex; align-items: center; gap: 8px; font-size: 13px; color: #374151; margin-bottom: 6px; }
.meta-type { display: inline-flex; align-items: center; gap: 8px; }
.meta-glyph { color: #374151; fill: none; flex: 0 0 auto; }
.sep { color: #9ca3af; }
.specialization-badge { font-style: italic; color: #6d28d9; }
.artifact-id { font-size: 11px; color: #9ca3af; }
.mono { font-family: monospace; }

.cancel-btn {
  padding: 7px 16px; background: #f3f4f6; color: #374151; border: 1px solid #d1d5db;
  border-radius: 6px; font-size: 13px; cursor: pointer;
}
.cancel-btn:hover:not(:disabled) { background: #e5e7eb; }
.preview-btn {
  padding: 7px 16px; background: #f3f4f6; color: #1d4ed8; border: 1px solid #bfdbfe;
  border-radius: 6px; font-size: 13px; cursor: pointer; font-weight: 500;
}
.preview-btn:hover:not(:disabled) { background: #eff6ff; }
.save-btn {
  padding: 7px 16px; background: #2563eb; color: white; border: none;
  border-radius: 6px; font-size: 13px; font-weight: 500; cursor: pointer;
}
.save-btn:hover:not(:disabled) { background: #1d4ed8; }
.cancel-btn:disabled, .preview-btn:disabled, .save-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.domain-badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 500; }
.domain--motivation { background: #d8c1e4; color: #252327; }
.domain--strategy   { background: #efbd5d; color: #252327; }
.domain--business   { background: #f4de7f; color: #252327; }
.domain--common     { background: #e8e5d3; color: #252327; }
.domain--application{ background: #b6d7e1; color: #252327; }
.domain--technology { background: #c3e1b4; color: #252327; }

.status-badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 500; }
.status--draft      { background: #f3f4f6; color: #6b7280; }
.status--active     { background: #dcfce7; color: #166534; }
.status--deprecated { background: #fee2e2; color: #991b1b; }
</style>
