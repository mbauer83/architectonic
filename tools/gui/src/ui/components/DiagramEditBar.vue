<script setup lang="ts">
/**
 * The bar over a diagram in edit mode: how it is arranged, Undo and Redo, what Save would write, and
 * Discard and Save — or, while leaving with unsaved changes, the choice of how to leave.
 *
 * Display and clicks only: the edit mode (`useDiagramEditMode`) decides and wires the keys.
 */
import { computed, nextTick, ref, watch } from 'vue'
import type { DiagramEditMode } from '../composables/useDiagramEditMode'
import { breachSentence, distinctBreaches } from '../../domain/layout/lab/labBreaches'
import { useEditingPreferences } from '../composables/useEditingPreferences'
import { arrowsAcross } from '../lib/arrowsAcross'
import { usePulse } from '../composables/usePulse'
import DiagramChangeList from './DiagramChangeList.vue'
import { useCanvasBoxes } from '../composables/useCanvasBoxes'
import { useCommandPermission } from '../composables/usePermissions'
import { DIAGRAM_OPERATIONS } from '../../domain/canvasCommands'

const props = defineProps<{ edit: DiagramEditMode }>()

const session = computed(() => props.edit.session)
const editing = computed(() => props.edit.editing)
const byHand = computed(() => session.value.state.value?.byHand ?? false)
const changes = computed(() => editing.value.changes.value)
const saving = computed(() => editing.value.saving.value)
const leaving = computed(() => props.edit.leaving.value)
const error = computed(() => editing.value.error.value)
const boxes = useCanvasBoxes(props.edit.editing)
const permit = useCommandPermission(DIAGRAM_OPERATIONS)
const toAutomatic = computed(() => permit.value('bar.return-to-automatic'))
const toAutomaticBoxes = computed(() => permit.value('bar.automatic-boxes'))
/** The layout's rule breaches as the canvas marks them, read only while they are asked for. */
const breaches = computed(() => (props.edit.checking.value ? distinctBreaches(session.value.breaches.value) : []))
const checkTitle = computed(() => {
  if (!props.edit.checking.value) return 'Check layout: mark where lines break the layout rules'
  const picture = session.value.geometry.value
  return breaches.value.length === 0 ? 'No layout rule is broken'
    : breaches.value.map(({ breach }) => breachSentence(breach, picture)).join('\n')
})

const listOpen = ref(false)
const confirmExit = ref(false)
/** Save shows the list first where the model changes, or always where the reader prefers (Q3). */
const prefs = useEditingPreferences()
const confirmFirst = computed(() => prefs.saveList.value.value === 'always' || changes.value.some(c => c.model))
const requestSave = (exit = false) => {
  if (confirmFirst.value) {
    confirmExit.value = exit
    listOpen.value = true
    props.edit.keepEditing()
  } else if (exit) void props.edit.saveAndExit()
  else void editing.value.save()
}
const confirm = async () => {
  if (confirmExit.value) await props.edit.saveAndExit()
  else await editing.value.save()
  listOpen.value = Boolean(editing.value.error.value)
  confirmExit.value = false
}
const saveAndExit = ref<HTMLButtonElement | null>(null)
/** The choice takes the focus on its first, safest answer, so Enter saves and Escape keeps editing. */
watch(leaving, async (asked) => { if (asked) { await nextTick(); saveAndExit.value?.focus() } })

defineExpose({
  /** Whether the list of changes is open; closing it is the first thing Escape does. */
  closeList: (): boolean => {
    const wasOpen = listOpen.value
    listOpen.value = false
    return wasOpen
  },
})

const plural = (count: number): string => `${count} change${count === 1 ? '' : 's'}`
/** How many of the changes go to the model, which the count beside Save names. */
const toTheModel = computed(() => changes.value.filter((change) => change.model).length)
/** Undo's and Redo's tooltips name the step each would take (sketch 01·6). */
const undoTitle = computed(() => {
  const step = editing.value.undoStep.value
  return step ? `Undo: ${step} (Ctrl+Z)` : 'Nothing to undo'
})
const redoTitle = computed(() => {
  const step = editing.value.redoStep.value
  return step ? `Redo: ${step} (Ctrl+Shift+Z)` : 'Nothing to redo'
})
/** The chip pulses when the picture changes hands; the count when a change joins it. */
const chip = usePulse(() => byHand.value)
const count = usePulse(
  () => [changes.value.length, toTheModel.value] as const,
  ([all, model], [allWas, modelWas]) => all > allWas || model > modelWas,
)
</script>

<template>
  <div
    class="edit-bar"
    data-testid="diagram-edit-bar"
  >
    <span
      class="state-chip"
      :class="{ hand: byHand, pulse: chip.pulsing.value }"
      data-testid="layout-state"
      @animationend="chip.settle()"
    >
      <template v-if="byHand">
        Arranged by hand ·
        <button
          type="button"
          data-testid="return-to-automatic"
          :disabled="!toAutomatic.allowed"
          :title="toAutomatic.allowed ? undefined : toAutomatic.reason"
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
      :title="undoTitle"
      data-testid="edit-undo"
      @click="session.undo()"
    >
      Undo
    </button>
    <button
      type="button"
      class="btn btn-plain btn-sm"
      :disabled="!edit.canRedo.value"
      :title="redoTitle"
      data-testid="edit-redo"
      @click="session.redo()"
    >
      Redo
    </button>
    <!-- The layer and type boxes are the diagram's own once one was edited (D9): this gives them back. -->
    <button
      v-if="boxes.owned.value"
      type="button"
      class="btn btn-plain btn-sm"
      :title="toAutomaticBoxes.allowed
        ? 'Drop the layer and type boxes written down for this diagram: they are drawn automatically again'
        : toAutomaticBoxes.reason"
      :disabled="!toAutomaticBoxes.allowed"
      data-testid="return-to-automatic-boxes"
      @click="boxes.automatic()"
    >
      Return to automatic boxes
    </button>
    <!-- Check layout (owner): as quiet as its neighbours, off until asked for; on, a count beside it and
         each breach named in its tooltip and on hover over its mark. -->
    <button
      type="button"
      class="btn btn-plain btn-sm check"
      :aria-pressed="edit.checking.value"
      :title="checkTitle"
      data-testid="edit-check-layout"
      @click="edit.toggleCheck()"
    >
      <svg
        viewBox="0 0 16 16"
        aria-hidden="true"
      ><rect
        x="2.5"
        y="2.5"
        width="11"
        height="11"
        rx="1.5"
        stroke-dasharray="2.5 2"
      /></svg>
      Check layout<span
        v-if="edit.checking.value"
        class="count"
        data-testid="edit-check-count"
      >{{ breaches.length }}</span>
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
        @keydown="arrowsAcross"
      >
        <strong>Discard and exit edit mode?</strong> {{ changes.length }} unsaved.
        <button
          ref="saveAndExit"
          type="button"
          class="btn btn-primary btn-sm"
          :disabled="saving"
          data-testid="save-and-exit"
          @click="requestSave(true)"
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
          :class="{ pulse: count.pulsing.value }"
          :aria-expanded="listOpen"
          data-testid="change-count"
          @click="listOpen = !listOpen"
          @animationend="count.settle()"
        >{{ plural(changes.length) }}<template v-if="toTheModel"> · <b>{{ toTheModel }} to the model</b></template>
          ▾</button>
        <DiagramChangeList
          v-if="listOpen"
          :changes="changes"
          :confirming="confirmFirst"
          :saving="saving"
          @confirm="confirm"
        />
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
        @click="requestSave()"
      >
        {{ saving ? 'Saving…' : 'Save' }}
      </button>
    </template>
    <span class="vr" />
    <!-- The panel beside the canvas, open or closed (owner, Q22): the panel icon, its right pane
         filled while the panel is open. -->
    <button
      type="button"
      class="panel-toggle"
      :class="{ on: edit.panel.open.value }"
      :aria-expanded="edit.panel.open.value"
      aria-label="Sidebar"
      title="Sidebar"
      data-testid="edit-panel-toggle"
      @click="edit.panel.toggle()"
    >
      <svg
        viewBox="0 0 20 16"
        aria-hidden="true"
      >
        <rect
          x="1"
          y="1"
          width="18"
          height="14"
          rx="2"
        />
        <line
          x1="12.5"
          y1="1"
          x2="12.5"
          y2="15"
        />
        <rect
          class="pane"
          x="12.5"
          y="1"
          width="6.5"
          height="14"
        />
      </svg>
    </button>
  </div>
</template>

<style scoped src="./DiagramEditBar.css"></style>
