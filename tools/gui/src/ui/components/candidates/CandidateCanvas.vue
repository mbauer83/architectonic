<script setup lang="ts">
/**
 * Sketching a candidate (06·5, F12, F14): the candidate's own picture in edit mode with the diagram page's own
 * editor (`CanvasContentEditor` over `DiagramCanvas`), in a candidate's words. The picture needs no stored
 * diagram: it starts from the one the candidate is drawn on, from a view of what it reads over, or empty
 * (`candidatePicture`). Beside it the edit panel's search and neighbourhood (`DiagramMemberPicker`) put model
 * elements on it, which the candidate then reads over; an empty candidate may start from a diagram or stack on a
 * candidate instead (`CandidateSeed`). A band names what is sketched, what it stacks on, and when it was last
 * saved to the candidate; there is no Save, because every change is recorded as it is made. *Edit details…*
 * opens on the element as the candidate holds it, marking what differs from what it stacks on
 * (`useCandidateDetails`). What the session created or renamed carries a small + or ~. *Undo* (and Ctrl+Z on
 * the canvas) takes back the last step, and with it what that step recorded in the candidate.
 */
import { computed, inject, onMounted, provide, ref, shallowRef, watch } from 'vue'
import { Effect } from 'effect'
import type { PictureContext } from '../../../domain'
import type { Marks } from '../../../domain/candidates/elementMarks'
import { stableEntityId } from '../../../domain/artifactId'
import { modelServiceKey } from '../../keys'
import { formatEffectError } from '../../lib/errors'
import { composedOver } from '../../../domain/candidates/candidateDrawing'
import { drawnByEntity, relationsDrawn } from '../../../domain/layout/canvasComposition'
import { useCandidateDetails } from '../../composables/useCandidateDetails'
import { useCandidateEditing } from '../../composables/useCandidateEditing'
import { useDrawnEntities } from '../../composables/useDrawnEntities'
import { useFittedPanZoom } from '../../composables/useFittedPanZoom'
import CanvasContentEditor from '../CanvasContentEditor.vue'
import { detailsSourceKey } from '../canvasDetails'
import { CANDIDATE_WORDS } from '../canvasWords'
import DiagramCanvas from '../canvas/DiagramCanvas.vue'
import ElementMarksLayer from './ElementMarksLayer.vue'
import CandidateSeed from './CandidateSeed.vue'
import DiagramMemberPicker from '../DiagramMemberPicker.vue'
import DiagramViewportOverlays from '../DiagramViewportOverlays.vue'
import { isTypingIn } from '../../lib/keyboardScheme'

/** *changed*: the candidate against its base, as the operations table reads it (~ and − on model elements). */
const props = withDefaults(defineProps<{
  candidateId: string; name: string; role: string; changed: Marks
  /** What it stacks on, in words (`stackLine`). */
  stack?: string
  /** What *Done sketching* says, where it leads somewhere: the naive architecture's points on to Stressors. */
  doneLabel?: string
}>(), { doneLabel: 'Done sketching', stack: '' })
const emit = defineEmits<{ recorded: []; done: [] }>()
const svc = inject(modelServiceKey)!
provide(detailsSourceKey, useCandidateDetails(svc, () => props.candidateId))

const context = shallowRef<PictureContext | null>(null)
const error = ref<string | null>(null)
const showChanges = ref(true)
/** The picture's context again: what is near the elements the candidate now reads over. */
const readContext = async () => {
  context.value = await Effect.runPromise(svc.readCandidatePictureContext(props.candidateId))
}
/** How many times the candidate was recorded in: the seed offer asks again whether it is still empty. */
const recordings = ref(0)
const recorded = () => {
  recordings.value += 1
  emit('recorded')
  void readContext().catch(() => undefined)
}
/** Where the session started from: read when it opens, so the context read later does not move it. */
const started = shallowRef<PictureContext['diagram'] | null>(null)
const editing = useCandidateEditing(
  svc, (start) => composedOver(started.value, start), () => props.candidateId, recorded,
)
/** The panel is open to begin with on a picture that starts empty, where finding elements is the first step. */
const panelOpen = ref(false)
const canvas = ref<InstanceType<typeof DiagramCanvas> | null>(null)
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
/** Ctrl+Z, Ctrl+Shift+Z and Ctrl+Y on the canvas, as on the diagram page. */
const onKey = (event: KeyboardEvent) => {
  if (!(event.ctrlKey || event.metaKey) || isTypingIn(event.target)) return
  const key = event.key.toLowerCase()
  if (key !== 'z' && key !== 'y') return
  event.preventDefault()
  if (key === 'y' || event.shiftKey) editing.session.redo()
  else editing.session.undo()
}

/** Read the picture and open the session on it: on mounting, and again once the candidate is seeded. */
const openCanvas = async () => {
  error.value = null
  try {
    await readContext()
    started.value = context.value?.diagram ?? null
    panelOpen.value = panelOpen.value || !started.value?.entity_ids_used?.length
    if (!(await editing.open())) error.value = editing.error.value ?? 'The canvas could not be opened.'
  } catch (failure) {
    error.value = formatEffectError(failure)
  }
}
const seeded = async () => {
  await openCanvas()
  emit('recorded')
}
onMounted(openCanvas)
</script>

<template>
  <div
    class="sketching"
    data-testid="candidate-canvas"
  >
    <!-- A note shown above the sketch (the naive architecture's introduction): inside the column, so the
         canvas is fitted to what the note leaves of it. -->
    <div
      v-if="$slots.intro"
      class="intro"
    >
      <slot name="intro" />
    </div>
    <div class="cs-banner">
      <span class="what">Sketching {{ name }}<small
        v-if="stack"
        class="stack"
        data-testid="sketch-stack"
      > · {{ stack }}</small></span>
      <span class="acts">
        <span
          v-if="editing.savedAt.value"
          class="saved"
          data-testid="saved-at"
        >Saved to the candidate {{ editing.savedAt.value }}</span>
        <span
          v-else
          class="saved"
        >Saved to the candidate as you sketch</span>
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
          class="btn btn-sm"
          data-testid="sketch-panel-toggle"
          :aria-pressed="panelOpen"
          @click="panelOpen = !panelOpen"
        >Add from model</button>
        <button
          type="button"
          class="btn btn-sm btn-primary"
          data-testid="done-sketching"
          @click="emit('done')"
        >{{ doneLabel }}</button>
      </span>
      <span class="kind">{{ role }} · candidate architecture · draft · right-click for the menu · double-click renames ·
        nothing reaches the model before it is applied</span>
    </div>
    <p
      v-if="error ?? editing.error.value"
      class="err"
      role="alert"
    >
      {{ error ?? editing.error.value }}
    </p>
    <div class="sketch-body">
      <div
        ref="containerRef"
        class="img-container editing viewport-host"
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
              @select="canvas?.select($event)"
            >
              <DiagramCanvas
                ref="canvas"
                :session="editing.session"
              >
                <ElementMarksLayer
                  :session="editing.session"
                  :entity-of="entityOf"
                  :marks="marks"
                  :tag-size="tagSize"
                />
              </DiagramCanvas>
            </CanvasContentEditor>
          </div>
        </div>
        <DiagramViewportOverlays
          :window="panZoom"
          :picture="svgContainer"
          hint="Scroll to zoom · Drag an element to move it · 0 fits"
        />
      </div>
      <aside
        v-if="panelOpen && context"
        class="sketch-panel card"
        aria-label="Add from model"
      >
        <CandidateSeed
          :key="recordings"
          :candidate-id="candidateId"
          @seeded="seeded"
        />
        <DiagramMemberPicker
          :context="context"
          :busy="editing.loading.value || editing.saving.value"
          :drawn="drawnByEntity(context, editing.session.state.value, editing.session.geometry.value)"
          :drawn-relations="relationsDrawn(context, editing.session.state.value)"
          @add="(entity) => editing.add(entity.artifact_id, entity.name, entity.artifact_type)"
          @draw="(id) => editing.drawRelation(id)"
          @select="(alias) => canvas?.select(alias)"
          @outline="() => undefined"
          @outward="panelOpen = false"
        />
      </aside>
    </div>
  </div>
</template>

<style scoped>
/*
 * Fitted to its pane: the sketch is as tall as the window leaves below the page's header, and the canvas takes
 * what the banner and any note above it (the `intro` slot) leave of that, so the bottom of the picture is never
 * below the window however either wraps in a narrow pane.
 */
.sketching { display: flex; flex-direction: column; height: clamp(480px, calc(100vh - 220px), 1240px); }
.intro { flex: none; }
.cs-banner {
  display: flex; flex-wrap: wrap; gap: 4px 10px; align-items: center; justify-content: space-between;
  padding: 7px 10px; margin-bottom: 8px; border: 1px solid var(--accent-border); background: var(--accent-soft);
  color: var(--accent-strong); border-radius: 6px; font-size: 12.5px; flex: none;
}
.what { font-size: 13.5px; font-weight: 700; }
.stack { font-size: 12px; font-weight: 400; color: var(--text-2); }
.kind { flex-basis: 100%; font-size: 12px; color: var(--text-2); }
.acts { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
.saved { font-size: 11.5px; color: var(--muted); }
.err { color: var(--danger-strong); font-size: 12.5px; flex: none; }
.img-container {
  position: relative; overflow: hidden; background: var(--paper); border: 1px solid var(--accent);
  box-shadow: inset 0 2px 0 var(--accent); border-radius: 8px; height: 100%;
}
/* The panel floats over the canvas's right edge, so the picture keeps the pane's whole width. */
.sketch-body { position: relative; flex: 1; min-height: 240px; }
.sketch-panel {
  position: absolute; top: 8px; right: 8px; bottom: 8px; width: min(280px, 45%); overflow: auto; z-index: 2;
  box-shadow: 0 4px 14px rgb(0 0 0 / 14%);
}
.svg-wrap :deep(svg) { display: block; max-width: none; }
</style>
