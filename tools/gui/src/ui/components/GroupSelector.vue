<script setup lang="ts">
import { computed } from 'vue'
import { useGroupManagement } from '../composables/useGroupManagement'

interface GroupOption {
  slug: string
  name: string
  count?: number
  archived?: boolean
}

const props = defineProps<{
  groups: GroupOption[]
  modelValue: string
  showArchived?: boolean
  manageable?: boolean
  axis?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [slug: string]
  'update:showArchived': [value: boolean]
  'group-mutated': []
  'navigate-to-groups': []
}>()

const mgmt = useGroupManagement({
  axis: props.axis ?? '',
  onMutated: () => emit('group-mutated'),
})

const visibleGroups = computed(() =>
  props.groups.filter(g => props.showArchived || !g.archived),
)

const select = (slug: string) => emit('update:modelValue', slug)
const toggleArchived = () => emit('update:showArchived', !props.showArchived)
</script>

<template>
  <div class="group-selector">
    <ul class="group-list">
      <li>
        <button
          class="group-btn"
          :class="{ active: modelValue === '' }"
          @click="emit('navigate-to-groups')"
        >
          All
        </button>
      </li>
      <li
        v-for="g in visibleGroups"
        :key="g.slug"
        class="group-item"
      >
        <button
          class="group-btn"
          :class="{ active: modelValue === g.slug, archived: g.archived }"
          :title="g.archived ? `${g.name} (archived)` : g.name"
          @click="select(g.slug)"
        >
          <span class="group-name">{{ g.name }}</span>
          <span
            v-if="g.count !== undefined"
            class="group-count"
          >{{ g.count }}</span>
        </button>
        <button
          v-if="manageable"
          class="item-menu-btn"
          title="Manage"
          @click.stop="mgmt.openRename(g)"
        >
          ⋯
        </button>
      </li>
    </ul>

    <div class="group-actions">
      <button
        v-if="manageable"
        class="action-btn"
        @click="mgmt.openCreate()"
      >
        + New
      </button>
      <button
        class="action-btn"
        :class="{ active: showArchived }"
        @click="toggleArchived"
      >
        {{ showArchived ? '− archived' : '+ archived' }}
      </button>
    </div>

    <!-- Dialogs -->
    <div
      v-if="mgmt.dialog.value === 'create'"
      class="group-dialog"
    >
      <div class="dialog-title">
        New Group
      </div>
      <label class="field">Name<input
        v-model="mgmt.fieldName.value"
        class="field-input"
        @input="mgmt.fieldSlug.value = mgmt.slugify(mgmt.fieldName.value)"
      ></label>
      <label class="field">Slug<input
        v-model="mgmt.fieldSlug.value"
        class="field-input"
      ></label>
      <div
        v-if="mgmt.dialogError.value"
        class="dialog-err"
      >
        {{ mgmt.dialogError.value }}
      </div>
      <div class="dialog-row">
        <button
          class="btn"
          @click="mgmt.closeDialog()"
        >
          Cancel
        </button>
        <button
          class="btn btn--primary"
          :disabled="mgmt.busy.value || !mgmt.fieldSlug.value || !mgmt.fieldName.value"
          @click="mgmt.submitCreate()"
        >
          Create
        </button>
      </div>
    </div>

    <div
      v-if="mgmt.dialog.value === 'rename'"
      class="group-dialog"
    >
      <div class="dialog-title">
        Rename "{{ mgmt.dialogTarget.value?.name }}"
      </div>
      <label class="field">Display name<input
        v-model="mgmt.fieldName.value"
        class="field-input"
      ></label>
      <div
        v-if="mgmt.dialogError.value"
        class="dialog-err"
      >
        {{ mgmt.dialogError.value }}
      </div>
      <div class="dialog-row">
        <button
          class="btn"
          @click="mgmt.closeDialog()"
        >
          Cancel
        </button>
        <button
          class="btn btn--primary"
          :disabled="mgmt.busy.value || !mgmt.fieldName.value"
          @click="mgmt.submitRename()"
        >
          Rename
        </button>
      </div>
    </div>

    <div
      v-if="mgmt.dialog.value === 'archive'"
      class="group-dialog"
    >
      <div class="dialog-title">
        {{ mgmt.dialogTarget.value?.archived ? 'Unarchive' : 'Archive' }} "{{ mgmt.dialogTarget.value?.name }}"
      </div>
      <p
        v-if="mgmt.archiveNeedsConfirm.value"
        class="dialog-note"
      >
        Has {{ mgmt.dialogTarget.value?.count }} items. Type slug to confirm:
      </p>
      <input
        v-if="mgmt.archiveNeedsConfirm.value"
        v-model="mgmt.fieldConfirm.value"
        class="field-input"
        :placeholder="mgmt.dialogTarget.value?.slug"
      >
      <div
        v-if="mgmt.dialogError.value"
        class="dialog-err"
      >
        {{ mgmt.dialogError.value }}
      </div>
      <div class="dialog-row">
        <button
          class="btn"
          @click="mgmt.closeDialog()"
        >
          Cancel
        </button>
        <button
          class="btn btn--primary"
          :disabled="mgmt.busy.value || !mgmt.archiveReady.value"
          @click="mgmt.submitArchive()"
        >
          {{ mgmt.dialogTarget.value?.archived ? 'Unarchive' : 'Archive' }}
        </button>
      </div>
    </div>

    <div
      v-if="mgmt.dialog.value === 'delete'"
      class="group-dialog"
    >
      <div class="dialog-title">
        Delete "{{ mgmt.dialogTarget.value?.name }}"
      </div>
      <p
        v-if="mgmt.deleteNeedsConfirm.value"
        class="dialog-note"
      >
        Has {{ mgmt.dialogTarget.value?.count }} items — all deleted. Type slug:
      </p>
      <input
        v-if="mgmt.deleteNeedsConfirm.value"
        v-model="mgmt.fieldConfirm.value"
        class="field-input"
        :placeholder="mgmt.dialogTarget.value?.slug"
      >
      <div
        v-if="mgmt.dialogError.value"
        class="dialog-err"
      >
        {{ mgmt.dialogError.value }}
      </div>
      <div class="dialog-row">
        <button
          class="btn"
          @click="mgmt.closeDialog()"
        >
          Cancel
        </button>
        <button
          class="btn btn--danger"
          :disabled="mgmt.busy.value || !mgmt.deleteReady.value"
          @click="mgmt.submitDelete()"
        >
          Delete
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.group-selector { display: flex; flex-direction: column; gap: 0.25rem; }
.group-list { list-style: none; display: flex; flex-direction: column; gap: 2px; }
.group-item { position: relative; display: flex; align-items: center; }

.group-btn {
  width: 100%; display: flex; align-items: center; justify-content: space-between;
  padding: 6px 10px; border: 0; border-left: 3px solid transparent;
  border-radius: 6px; background: transparent; color: #374151;
  cursor: pointer; font-size: 13px; text-align: left;
}
.group-btn:hover { background: #f3f4f6; }
.group-btn.active { background: #eff6ff; color: #1d4ed8; font-weight: 500; border-left-color: #2563eb; }
.group-btn.archived { opacity: 0.55; }
.group-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.group-count { font-size: 11px; color: #9ca3af; margin-left: 4px; flex-shrink: 0; }

.item-menu-btn {
  flex-shrink: 0; width: 18px; height: 18px; border-radius: 4px; border: 1px solid #d1d5db;
  background: white; font-size: 10px; cursor: pointer; display: none;
  align-items: center; justify-content: center; line-height: 1; color: #374151; margin-left: 2px;
}
.group-item:hover .item-menu-btn { display: flex; }

.group-actions { display: flex; gap: 4px; margin-top: 4px; flex-wrap: wrap; }
.action-btn {
  padding: 3px 8px; border: 1px dashed #d1d5db; border-radius: 4px;
  background: transparent; font-size: 11px; color: #6b7280; cursor: pointer;
}
.action-btn:hover { background: #f3f4f6; }
.action-btn.active { color: #2563eb; border-color: #2563eb; }

.group-dialog {
  background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px;
  padding: 12px; display: flex; flex-direction: column; gap: 8px; margin-top: 4px;
}
.dialog-title { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #374151; }
.dialog-note { font-size: 11px; color: #6b7280; margin: 0; }
.field { display: flex; flex-direction: column; gap: 2px; font-size: 10px; color: #6b7280; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; }
.field-input { padding: 4px 8px; border: 1px solid #d1d5db; border-radius: 4px; font-size: 12px; }
.dialog-err { font-size: 11px; color: #dc2626; }
.dialog-row { display: flex; gap: 6px; justify-content: flex-end; }
.btn { padding: 4px 10px; border: 1px solid #d1d5db; border-radius: 4px; background: white; cursor: pointer; font-size: 12px; }
.btn--primary { background: #2563eb; color: white; border-color: #2563eb; }
.btn--primary:hover:not(:disabled) { background: #1d4ed8; }
.btn--danger { background: #dc2626; color: white; border-color: #dc2626; }
.btn--danger:hover:not(:disabled) { background: #b91c1c; }
.btn:disabled { opacity: 0.5; cursor: not-allowed; }
</style>
