<script setup lang="ts">
import { computed } from 'vue'
import { entityGraphRoute } from '../router/artifactRoutes'

import ProposedBadge from './ProposedBadge.vue'
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
import { editBlockedReason, editOutcome, editOutcomeTitle } from '../lib/entityEditBlocking'

const props = defineProps<{
  detail: EntityDetail
  entityId: string
  backTo: RouteLocationRaw
  adminMode: boolean
  isGlobalEntity: boolean
}>()
const emit = defineEmits<{ delete: [] }>()
const edit = inject(entityEditFormKey)!
// What pressing Edit will do here — the same question the form card answers in words.
const outcome = computed(() => editOutcome(props.isGlobalEntity, props.adminMode))
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
        <ProposedBadge :standing="detail.baseline_standing" />
        <RouterLink
          :to="entityGraphRoute(entityId)"
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
          v-if="!edit.editing"
          class="edit-btn"
          :class="{ 'edit-btn--admin': outcome === 'writes-upstream' }"
          :title="editOutcomeTitle(outcome)"
          @click="edit.startEdit()"
        >
          Edit{{ outcome === 'writes-upstream' ? ' ⚠' : '' }}
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
        <template
          v-for="spec in detail.specializations"
          :key="spec"
        >
          <span class="sep">·</span>
          <span class="specialization-badge">«{{ spec }}»</span>
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
.back-link { font-size: 13px; color: var(--muted); }
.back-link:hover { color: var(--text-2); }
.top-actions { display: flex; gap: 8px; align-items: center; }

.graph-btn {
  padding: 6px 14px; border-radius: 6px; background: var(--inverse); color: var(--on-inverse);
  font-size: 13px; font-weight: 500;
}
.graph-btn:hover { background: var(--inverse-hover); text-decoration: none; }

.edit-btn {
  padding: 6px 14px; border-radius: 6px; background: var(--soft); color: var(--text-2);
  border: 1px solid var(--border-strong); font-size: 13px; font-weight: 500; cursor: pointer;
}
.edit-btn:hover { background: var(--border); }
.delete-btn {
  padding: 6px 14px; border-radius: 6px; background: var(--danger-soft); color: var(--danger-strong);
  border: 1px solid var(--danger-border); font-size: 13px; font-weight: 500; cursor: pointer;
}
.delete-btn:hover { background: var(--danger-soft); }

.promote-btn {
  padding: 6px 14px; border-radius: 6px; background: var(--warn-soft); color: var(--warn-text);
  border: 1px solid var(--warn-border); font-size: 13px; font-weight: 500;
}
.promote-btn:hover { background: var(--warn-border); text-decoration: none; }

.edit-btn--admin {
  background: #7c2d12; color: #fed7aa; border-color: #ea580c;
}
.edit-btn--admin:hover { background: #9a3412; }

.global-badge {
  display: inline-block;
  background: var(--warn-soft); color: var(--warn-text);
  border: 1px solid var(--warn-border); border-radius: 4px;
  padding: 2px 8px; font-size: 11px; font-weight: 700;
  text-transform: uppercase; letter-spacing: .05em;
}

.entity-header { margin-bottom: 20px; }
.entity-title-row { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; flex-wrap: wrap; }
.entity-name { font-size: 22px; font-weight: 700; }
.edit-name-input {
  font-size: 20px; font-weight: 600; border: 1px solid var(--border-strong); border-radius: 6px;
  padding: 4px 10px; outline: none; flex: 1;
}
.edit-name-input:focus { border-color: var(--accent); }
.edit-status-select {
  padding: 3px 8px; border-radius: 6px; border: 1px solid var(--border-strong); font-size: 12px; outline: none;
}

.meta-row { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--text-2); margin-bottom: 6px; }
.meta-type { display: inline-flex; align-items: center; gap: 8px; }
.meta-glyph { color: var(--text-2); fill: none; flex: 0 0 auto; }
.sep { color: var(--faint); }
.specialization-badge { font-style: italic; color: var(--violet-text); }
.artifact-id { font-size: 11px; color: var(--faint); }
.mono { font-family: monospace; }

.cancel-btn {
  padding: 7px 16px; background: var(--soft); color: var(--text-2); border: 1px solid var(--border-strong);
  border-radius: 6px; font-size: 13px; cursor: pointer;
}
.cancel-btn:hover:not(:disabled) { background: var(--border); }
.preview-btn {
  padding: 7px 16px; background: var(--soft); color: var(--accent-strong); border: 1px solid var(--accent-border);
  border-radius: 6px; font-size: 13px; cursor: pointer; font-weight: 500;
}
.preview-btn:hover:not(:disabled) { background: var(--accent-soft); }
.save-btn {
  padding: 7px 16px; background: var(--accent); color: var(--on-accent); border: none;
  border-radius: 6px; font-size: 13px; font-weight: 500; cursor: pointer;
}
.save-btn:hover:not(:disabled) { background: var(--accent-strong); }
.cancel-btn:disabled, .preview-btn:disabled, .save-btn:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
