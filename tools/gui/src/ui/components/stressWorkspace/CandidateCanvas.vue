<script setup lang="ts">
/**
 * Sketching a candidate (06·5, F12, F14): the scope diagram in edit mode with the diagram page's own
 * editor (`CanvasContentEditor` over `LayoutLabCanvas`), in a candidate's words. A band names what is
 * sketched and when it was last saved to the candidate; there is no Save, because every change is
 * recorded as it is made. What the session created or renamed carries a small + or ~. *Undo* (and
 * Ctrl+Z on the canvas) takes back the last step, and with it what that step recorded in the candidate.
 */
import { computed, inject, onMounted, ref, shallowRef, watch } from 'vue'
import { Effect } from 'effect'
import type { DiagramContext } from '../../../domain'
import type { Marks } from '../../../domain/stressAnalysis/workspaceMarks'
import { stableEntityId } from '../../../domain/artifactId'
import { modelServiceKey } from '../../keys'
import { formatEffectError } from '../../lib/errors'
import { membershipOf } from '../../../domain/layout/diagramMembership'
import { useCandidateEditing } from '../../composables/useCandidateEditing'
import { useDrawnEntities } from '../../composables/useDrawnEntities'
import { useFittedPanZoom } from '../../composables/useFittedPanZoom'
import CanvasContentEditor from '../CanvasContentEditor.vue'
import { CANDIDATE_WORDS } from '../canvasWords'
import LayoutLabCanvas from '../layoutLab/LayoutLabCanvas.vue'
import WorkspaceMarksLayer from './WorkspaceMarksLayer.vue'

/** *changed*: the candidate against its base, as the operations table reads it (~ and − on model elements). */
const props = defineProps<{ candidateId: string; name: string; role: string; diagramId: string; changed: Marks }>()
const emit = defineEmits<{ recorded: []; done: [] }>()
const svc = inject(modelServiceKey)!

const context = shallowRef<DiagramContext | null>(null)
const error = ref<string | null>(null)
const showChanges = ref(true)
const editing = useCandidateEditing(
  svc, () => props.diagramId, () => membershipOf(context.value?.diagram ?? null), () => props.candidateId,
  () => emit('recorded'),
)
const canvas = ref<InstanceType<typeof LayoutLabCanvas> | null>(null)
const entityOf = useDrawnEntities(() => context.value, () => editing.session.geometry.value)

/** F14: what the candidate changed, and what it creates (+), drawn by the id the canvas gave it. */
const created = computed(() => (editing.session.state.value?.commands ?? [])
  .flatMap((command) => (command.op === 'model.element.create' ? [command.artifact_id] : [])))
const marks = computed((): Marks => (showChanges.value
  ? new Map([...props.changed, ...created.value.map((id) =>
    [stableEntityId(id), { kind: 'added' as const, tag: '+', title: 'Created in this candidate' }] as const)])
  : new Map()))

const containerRef = ref<HTMLElement | null>(null)
const svgContainer = ref<HTMLElement | null>(null)
const panZoom = useFittedPanZoom(containerRef, svgContainer)
watch(() => editing.session.geometry.value, () => { void panZoom.fitDiagramToViewport() })
const tagSize = computed(() => 14 / Math.max(panZoom.scale.value, 0.05))

const canUndo = computed(() => editing.session.history.value.length > 0)
const canRedo = computed(() => editing.session.future.value.length > 0)
const typing = (target: EventTarget | null): boolean =>
  target instanceof HTMLElement
  && (target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName))
/** Ctrl+Z, Ctrl+Shift+Z and Ctrl+Y on the canvas, as on the diagram page. */
const onKey = (event: KeyboardEvent) => {
  if (!(event.ctrlKey || event.metaKey) || typing(event.target)) return
  const key = event.key.toLowerCase()
  if (key !== 'z' && key !== 'y') return
  event.preventDefault()
  if (key === 'y' || event.shiftKey) editing.session.redo()
  else editing.session.undo()
}

onMounted(async () => {
  try {
    context.value = await Effect.runPromise(svc.getDiagramContext(props.diagramId))
    if (!(await editing.open())) error.value = editing.error.value ?? 'The canvas could not be opened.'
  } catch (failure) {
    error.value = formatEffectError(failure)
  }
})
</script>

<template>
  <div
    class="sketching"
    data-testid="candidate-canvas"
  >
    <div class="cs-banner">
      <span class="what">Sketching {{ name }}</span>
      <span class="acts">
        <span
          v-if="editing.savedAt.value"
          class="saved"
          data-testid="saved-at"
        >Saved to the candidate {{ editing.savedAt.value }}</span>
        <button
          type="button"
          class="btn btn-sm"
          data-testid="undo-sketch"
          :disabled="!canUndo"
          title="Undo the last change, and what it recorded in the candidate (Ctrl+Z)"
          @click="editing.session.undo()"
        >Undo</button>
        <button
          type="button"
          class="btn btn-sm"
          :disabled="!canRedo"
          title="Redo (Ctrl+Shift+Z)"
          @click="editing.session.redo()"
        >Redo</button>
        <button
          type="button"
          class="btn btn-sm"
          :aria-pressed="showChanges"
          @click="showChanges = !showChanges"
        >Show changes</button>
        <button
          type="button"
          class="btn btn-sm btn-primary"
          data-testid="done-sketching"
          @click="emit('done')"
        >Done sketching</button>
      </span>
      <span class="kind">{{ role }} · candidate architecture · draft · right-click for the menu · double-click renames ·
        nothing reaches the model before Commit</span>
    </div>
    <p
      v-if="error ?? editing.error.value"
      class="err"
      role="alert"
    >
      {{ error ?? editing.error.value }}
    </p>
    <div
      ref="containerRef"
      class="img-container editing"
      @keydown="onKey"
    >
      <div
        class="pan-canvas"
        :style="panZoom.canvasStyle.value"
      >
        <div
          v-if="context && editing.session.geometry.value"
          ref="svgContainer"
          class="svg-wrap"
        >
          <CanvasContentEditor
            :editing="editing"
            :context="context"
            :selection="canvas?.selected"
            :selected-shapes="canvas?.selection"
            :words="CANDIDATE_WORDS"
          >
            <LayoutLabCanvas
              ref="canvas"
              :session="editing.session"
            >
              <WorkspaceMarksLayer
                :session="editing.session"
                :entity-of="entityOf"
                :marks="marks"
                :tag-size="tagSize"
              />
            </LayoutLabCanvas>
          </CanvasContentEditor>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.cs-banner {
  display: grid; grid-template-columns: 1fr auto; gap: 2px 10px; align-items: center; padding: 7px 10px;
  margin-bottom: 8px; border: 1px solid var(--accent-border); background: var(--accent-soft);
  color: var(--accent-strong); border-radius: 6px; font-size: 12.5px;
}
.what { font-size: 13.5px; font-weight: 700; }
.kind { grid-column: 1 / -1; font-size: 12px; color: var(--text-2); }
.acts { grid-row: 1; grid-column: 2; display: flex; gap: 6px; align-items: center; }
.saved { font-size: 11.5px; color: var(--muted); }
.err { color: var(--danger-strong); font-size: 12.5px; }
.img-container {
  position: relative; overflow: hidden; background: var(--paper); border: 1px solid var(--accent);
  box-shadow: inset 0 2px 0 var(--accent); border-radius: 8px; height: clamp(380px, calc(100vh - 340px), 900px);
}
.svg-wrap :deep(svg) { display: block; max-width: none; }
</style>
