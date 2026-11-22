<script setup lang="ts">
/**
 * The bar over a diagram in edit mode: how it is arranged, Undo and Redo, what Save would write, and
 * Discard and Save — or, while leaving with unsaved changes, the choice of how to leave.
 *
 * Display and clicks only: the edit mode (`useDiagramEditMode`) decides and wires the keys.
 */
import { computed, nextTick, ref, watch } from 'vue'
import type { DiagramEditMode } from '../composables/useDiagramEditMode'

const props = defineProps<{ edit: DiagramEditMode }>()

const session = computed(() => props.edit.session)
const editing = computed(() => props.edit.editing)
const byHand = computed(() => session.value.state.value?.byHand ?? false)
const changes = computed(() => editing.value.changes.value)
const saving = computed(() => editing.value.saving.value)
const leaving = computed(() => props.edit.leaving.value)
const error = computed(() => editing.value.error.value)

const listOpen = ref(false)
const saveAndExit = ref<HTMLButtonElement | null>(null)

/** The choice takes the focus on its first, safest answer, so Enter saves and Escape keeps editing. */
watch(leaving, async (asked) => {
  if (!asked) return
  await nextTick()
  saveAndExit.value?.focus()
})

defineExpose({
  /** Whether the list of changes is open; closing it is the first thing Escape does. */
  closeList: (): boolean => {
    const wasOpen = listOpen.value
    listOpen.value = false
    return wasOpen
  },
})

const plural = (count: number): string => `${count} change${count === 1 ? '' : 's'}`
</script>

<template>
  <div
    class="edit-bar"
    data-testid="diagram-edit-bar"
  >
    <span
      class="state-chip"
      :class="{ hand: byHand }"
      data-testid="layout-state"
    >
      <template v-if="byHand">
        Arranged by hand ·
        <button
          type="button"
          data-testid="return-to-automatic"
          @click="editing.returnToAutomatic()"
        >Return to automatic</button>
      </template>
      <template v-else>Automatic layout</template>
    </span>
    <span class="vr" />
    <button
      type="button"
      class="btn btn-plain btn-sm"
      :disabled="!edit.canUndo.value"
      title="Undo (Ctrl+Z)"
      data-testid="edit-undo"
      @click="session.undo()"
    >
      Undo
    </button>
    <button
      type="button"
      class="btn btn-plain btn-sm"
      :disabled="!edit.canRedo.value"
      title="Redo (Ctrl+Shift+Z)"
      data-testid="edit-redo"
      @click="session.redo()"
    >
      Redo
    </button>
    <span class="sp" />
    <span
      v-if="error"
      class="err"
      role="alert"
    >{{ error }}</span>
    <template v-if="leaving">
      <span
        class="leave"
        role="group"
        aria-label="Leaving edit mode"
        data-testid="leave-choice"
      >
        <strong>Discard and exit edit mode?</strong> {{ changes.length }} unsaved.
        <button
          ref="saveAndExit"
          type="button"
          class="btn btn-primary btn-sm"
          :disabled="saving"
          data-testid="save-and-exit"
          @click="void edit.saveAndExit()"
        >Save and exit</button>
        <button
          type="button"
          class="btn btn-danger btn-sm"
          data-testid="discard-and-exit"
          @click="edit.discardAndExit()"
        >Discard and exit</button>
        <button
          type="button"
          class="btn btn-plain btn-sm"
          data-testid="keep-editing"
          @click="edit.keepEditing()"
        >Keep editing <kbd>Esc</kbd></button>
      </span>
    </template>
    <template v-else>
      <span
        v-if="changes.length === 0"
        class="none"
        data-testid="change-count"
      >No changes</span>
      <span
        v-else
        class="changes"
      >
        <button
          type="button"
          class="summary"
          :aria-expanded="listOpen"
          data-testid="change-count"
          @click="listOpen = !listOpen"
        >{{ plural(changes.length) }} ▾</button>
        <div
          v-if="listOpen"
          class="pop"
          role="dialog"
          aria-label="What Save will write"
          data-testid="change-list"
        >
          <h3>Save will write</h3>
          <p class="group"><span class="tag">Diagram</span> {{ plural(changes.length) }} to this diagram only</p>
          <ul>
            <li
              v-for="change in changes"
              :key="change.key"
            >{{ change.text }}</li>
          </ul>
        </div>
      </span>
      <button
        type="button"
        class="btn btn-plain btn-sm"
        :disabled="changes.length === 0 || saving"
        data-testid="edit-discard"
        @click="editing.discard()"
      >
        Discard
      </button>
      <button
        type="button"
        class="btn btn-primary btn-sm"
        :disabled="changes.length === 0 || saving"
        data-testid="edit-save"
        @click="void editing.save()"
      >
        {{ saving ? 'Saving…' : 'Save' }}
      </button>
    </template>
  </div>
</template>

<style scoped>
.edit-bar {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 6px 10px; margin-bottom: 8px;
  background: var(--surface); border: 1px solid var(--border); border-radius: 8px; font-size: 12.5px;
  color: var(--text-2);
}
.sp { flex: 1; }
.vr { width: 1px; align-self: stretch; background: var(--border); }
.state-chip {
  display: inline-flex; align-items: center; gap: 6px; padding: 2px 8px; border-radius: 4px;
  font-size: 11.5px; font-weight: 500; background: var(--soft); color: var(--text-2);
}
.state-chip.hand { background: var(--accent-soft); color: var(--accent-strong); }
.state-chip button {
  background: none; border: none; color: inherit; text-decoration: underline; cursor: pointer;
  font-size: 11.5px; padding: 0;
}
.btn {
  padding: 3px 10px; border: 1px solid var(--border-strong); border-radius: 6px; font-size: 12px;
  font-weight: 500; color: var(--text-2); cursor: pointer; white-space: nowrap; background: var(--soft);
}
.btn:disabled { opacity: 0.45; cursor: default; }
.btn-plain { background: var(--surface); }
.btn-plain:hover:not(:disabled) { background: var(--hover); }
.btn-primary { background: var(--accent); border-color: var(--accent); color: var(--on-accent); }
.btn-primary:hover:not(:disabled) { background: var(--accent-strong); }
.btn-danger { background: var(--surface); border-color: var(--danger-border); color: var(--danger-strong); }
kbd {
  font: 10px ui-monospace, monospace; padding: 0 4px; margin-left: 4px; border: 1px solid var(--border-strong);
  border-bottom-width: 2px; border-radius: 3px; background: var(--surface);
}
.none { color: var(--accent-strong); padding: 3px 8px; }
.changes { position: relative; }
.summary {
  background: none; border: none; cursor: pointer; padding: 3px 8px; border-radius: 5px; color: var(--accent-strong);
  font-size: 12.5px;
}
.summary:hover { background: var(--accent-soft); }
.pop {
  position: absolute; right: 0; top: calc(100% + 6px); z-index: 20; width: 400px; padding: 10px 12px;
  background: var(--surface); border: 1px solid var(--border-strong); border-radius: 8px; box-shadow: var(--shadow);
  color: var(--text);
}
.pop h3 { font-size: 13px; margin: 0 0 6px; }
.pop .group { font-weight: 600; margin: 0 0 4px; }
.pop .tag {
  background: var(--soft); color: var(--text-2); border-radius: 3px; padding: 1px 6px; font-size: 11px;
  margin-right: 4px;
}
.pop ul { margin: 0 0 6px 16px; padding: 0; }
.pop li { margin-bottom: 3px; }
.leave {
  display: inline-flex; align-items: center; gap: 6px; padding: 3px 8px; border-radius: 6px;
  background: var(--warn-soft); color: var(--warn-text); border: 1px solid var(--warn-border);
}
.err { color: var(--danger-strong); }
</style>
