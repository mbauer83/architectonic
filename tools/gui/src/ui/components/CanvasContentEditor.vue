<script setup lang="ts">
import { computed, inject, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import type { PictureContext } from '../../domain'
import { canvasMembers } from '../../domain/layout/canvasComposition'
import { modelServiceKey, toastKey } from '../keys'
import { useDropFeedback } from '../composables/useDropFeedback'
import { useEntityDrop } from '../composables/useEntityDrop'
import CanvasGestureCues from './CanvasGestureCues.vue'
import type { DiagramEditing } from '../composables/useDiagramEditing'
import type { CanvasCommand } from '../../ports/diagramWriteBodies'
import { elementAt, useContentGestures } from '../composables/useContentGestures'
import { useCanvasPopover } from '../composables/useCanvasPopover'
import { useOverlayHost } from '../composables/useOverlayHost'
import { useCanvasRelation } from '../composables/useCanvasRelation'
import { useCanvasNesting } from '../composables/useCanvasNesting'
import { useCanvasCreate } from '../composables/useCanvasCreate'
import CanvasElementForm from './CanvasElementForm.vue'
import CanvasSelectionMenu from './CanvasSelectionMenu.vue'
import CanvasLineMenu from './CanvasLineMenu.vue'
import CanvasMenu from './CanvasMenu.vue'
import CanvasConnectTarget from './CanvasConnectTarget.vue'
import CanvasRelationForm from './CanvasRelationForm.vue'
import CanvasRenameForm from './CanvasRenameForm.vue'
import CanvasDeleteConfirm from './CanvasDeleteConfirm.vue'
import CanvasDetailsDialog from './CanvasDetailsDialog.vue'
import { elementMenuItems, restackOf } from './canvasElementMenu'
import { entityDetailRoute } from '../router/artifactRoutes'
import CanvasNestTarget from './CanvasNestTarget.vue'
import { useDiagramTypeCapabilities } from '../composables/useDiagramTypeCapabilities'
import { isOnALine } from './lineMenuPlace'
import { useCanvasEditorKeys } from '../composables/useCanvasEditorKeys'
import { isGroupingBox } from '../../domain/layout/canvasBoxes'
import CanvasBoxMenu from './CanvasBoxMenu.vue'
import CanvasLabelForm from './CanvasLabelForm.vue'
import { type CanvasWords, DIAGRAM_WORDS } from './canvasWords'
import { useCommandGate } from '../composables/usePermissions'

const props = defineProps<{
  editing: DiagramEditing
  context: PictureContext
  selection?: string | null
  /** The line selected on the canvas, by its place on the picture: its menu is the line's. */
  line?: number | null
  /** Every shape selected: two or more open the selection's menu rather than an element's. */
  selectedShapes?: readonly string[]
  /** What deleting means here; the diagram page's words when absent. */
  words?: CanvasWords
  /** The shape the keyboard is on, as it is announced (`useCanvasFocus`). */
  focused?: string
}>()
/** *select*: what the editor added, which the canvas then selects so the arrows move it. */
const emit = defineEmits<{ select: [alias: string] }>()
const words = computed(() => props.words ?? DIAGRAM_WORDS)
const several = computed(() => props.selectedShapes ?? [])
const svc = inject(modelServiceKey)!
const router = useRouter()
const host = ref<HTMLElement | null>(null)
const pop = ref<HTMLElement | null>(null)
const { mode, at, error, width, position, close } = useCanvasPopover(host, pop)
const [source, target] = [ref(''), ref('')]
const members = computed(() =>
  canvasMembers(props.context, props.editing.session.state.value, props.editing.session.geometry.value))
const selected = computed(() => members.value.find((e) => e.alias === source.value))
const nameOf = (alias: string) => members.value.find((e) => e.alias === alias)?.name ?? alias
const drafted = computed(() => props.editing.session.state.value?.commands?.some(
  (c) => c.op === 'model.element.create' && c.artifact_id === selected.value?.id) ?? false)

/** A step the session took closes the popover; one it refused says why, there. Answers which it was. */
async function settle(step: Promise<boolean>): Promise<boolean> {
  const kept = await step
  if (kept) close(true)
  else error.value = props.editing.error.value ?? 'The drawing has changed. Try again.'
  return kept
}
const apply = (c: CanvasCommand, overlay?: Record<string, unknown>) => settle(props.editing.propose(c, overlay))
const toast = inject(toastKey, () => undefined)
const gated = useCommandGate(words.value.operations, (reason) => toast(reason, 'warn'))
const drop = useDropFeedback(svc, props.editing, host, () => props.context, members)
const relation = useCanvasRelation(
  svc, props.editing, () => props.context, members, { source, target },
  () => { mode.value = 'relation' }, (message) => { error.value = message }, (c, overlay) => void apply(c, overlay),
  (id, overlay) => void settle(props.editing.drawRelation(id, overlay)),
)
const { kind, drawing, inModel, label, srcCount, tgtCount, description, options, currentLine } = relation
const { anchor, drawAgain, ownBoxes, boxOfSelected, nestIn, nestUnder, asked, dropped, dontNest } = useCanvasNesting(
  props.editing, host, source, members, { mode, error, position, close }, (c) => apply(c), {
    settled: drop.settled, say: (line) => toast(line, 'info', 6000),
    nested: (part, whole) => words.value.nested(part, whole),
  },
)
const adding = useCanvasCreate(
  props.editing, host, () => props.context, members, { mode, error, close, source, asked },
  (alias) => emit('select', alias),
)
const typeCan = useDiagramTypeCapabilities(svc)
const drawsAgain = computed(() => typeCan(props.context.diagram.diagram_type, 'draws_occurrences'))

function rename(alias: string) {
  source.value = alias
  if (selected.value) mode.value = 'rename'
}
function onElement(choice: string) {
  const el = selected.value
  if (!el) return
  const how = restackOf(choice)
  if (how) {
    props.editing.restack([source.value], how)
    close(true)
  } else if (choice === 'rename') rename(source.value)
  else if (choice === 'connect') mode.value = 'target'
  else if (choice === 'nest') mode.value = 'nest'
  else if (choice === 'occurrence') void drawAgain()
  else if (choice === 'unnest') void nestIn(null)
  else if (choice === 'details') {
    details.value = el.id
    close()
  }
  else if (choice === 'delete') mode.value = 'delete'
  else if (choice === 'discard') void settle(props.editing.discardDraft(el.id))
  else if (choice === 'open') {
    window.open(router.resolve(entityDetailRoute(el.id)).href, '_blank', 'noopener')
    close()
  } else if (choice === 'remove') {
    props.editing.remove([source.value])
    close(true)
  }
}
/** What an element may be nested in: every other element, each once, however often it is drawn. */
const containersFor = (element: { readonly id: string }) => [...new Map(members.value
  .filter((m) => m.id !== element.id && !ownBoxes.value.some((box) => box.alias === m.alias))
  .map((m) => [m.id, m])).values()]
/** The element whose details are being edited in the modal; null while none is. */
const details = ref<string | null>(null)
const keepDetails = async (commands: readonly CanvasCommand[]): Promise<string | null> =>
  await props.editing.propose(commands) ? null : props.editing.error.value ?? 'The drawing has changed. Try again.'
const panelDrop = useEntityDrop(host, props.editing)
/** Adding by the menu on empty paper, or by a row dropped from the panel, as the permission answer allows. */
const add = { created: gated('canvas.create', adding.created), found: gated('canvas.place', adding.found),
  again: gated('element.occurrence', adding.again), dropped: gated('canvas.place', panelDrop.drop) }
function menu(event: MouseEvent) {
  event.preventDefault()
  position(event.clientX, event.clientY)
  anchor.value = { x: event.clientX, y: event.clientY }
  source.value = elementAt(event)?.dataset.alias ?? ''
  if (props.line != null && isOnALine(event.target)) {
    mode.value = 'line'
    return
  }
  // A box's title band opens the box's menu; its body, as empty paper's, adds to it (A-02.39, 03·1).
  if ((event.target as Element).classList.contains('lab-grip') && openMenu('box', source.value)) return
  const onSelection = several.value.length > 1 && (!source.value || several.value.includes(source.value))
  // A container element's body, below its title, is a box's body: the menu there adds to it (03·2).
  const box = adding.openedAt(event)
  const inContainer = box?.alias === source.value && (event.target as Element).classList.contains('lab-body')
  mode.value = onSelection ? 'selection' : selected.value && !inContainer ? 'element' : 'create'
}
// A line's menu belongs to the line it was opened on: another line picked, or none, closes it.
watch(() => props.line, () => { if (mode.value === 'line') close() })
/** The relation whose label is typed in place (02·5); null while none is. */
const labelling = ref<ReturnType<typeof relation.labelOf>>(null)
const relabel = (index: number) => {
  labelling.value = relation.labelOf(index)
  if (labelling.value) mode.value = 'label'
}
const keepLabel = (text: string) => labelling.value && void settle(props.editing.propose([], {
  artifact_id: labelling.value.id, label: text, include_multiplicity: true,
}))
const { focusCanvas, up, release, moving, leave, side } = useContentGestures(
  host, props.editing, source, position, gated('gesture.rename', rename), gated('line.edit', relation.editLine),
  gated('gesture.connect', (alias: string) => void relation.pair(alias)),
  gated('gesture.nest', (alias: string, target: string, x: number, y: number) => void dropped(alias, target, x, y)),
  drop.over, gated('line.relabel', relabel),
)
const { key, double, openMenu, boxAt } = useCanvasEditorKeys({
  host, mode, source, close, position, rename: gated('element.rename', rename),
  editLine: gated('line.edit', relation.editLine),
  selected: () => ({ line: props.line ?? null, shape: props.selection ?? null, shapes: several.value }),
  // One of the diagram's own boxes, where the page edits them, has a menu of its own (A-02.39).
  boxNamed: (alias) => (words.value.newBoxEntry === undefined ? undefined
    : props.editing.session.geometry.value?.boxes.find((one) => one.alias === alias && isGroupingBox(one))),
})
// Where the menus and cues open: inside the canvas while it has the screen (`useOverlayHost`).
const overlayHost = useOverlayHost()
</script>
<template>
  <div
    ref="host"
    class="content-canvas"
    :class="{ 'edge-hover': side, 'drop-lit': panelDrop.lit.value }"
    tabindex="0"
    @keydown="key"
    @dragover="panelDrop.over"
    @dragleave="panelDrop.leave"
    @drop="add.dropped"
    @contextmenu="menu"
    @dblclick="double"
    @pointerdown.capture="focusCanvas"
    @pointerup.capture="up"
    @pointercancel="release"
    @pointermove="moving"
    @pointerleave="leave"
  >
    <slot />
    <Teleport :to="overlayHost">
      <CanvasGestureCues
        :side="side"
        :lit="drop.lit.value"
      />
    </Teleport>
    <p
      class="live"
      aria-live="polite"
      data-testid="selection-announcement"
    >
      {{ several.length > 1 ? `${several.length} items selected` : (focused ?? '') }}
    </p>
    <CanvasDetailsDialog
      v-if="details"
      :key="details"
      :artifact-id="details"
      :pending="editing.session.state.value?.commands ?? []"
      :keep="keepDetails"
      @close="details = null; host?.focus({ preventScroll: true })"
    />
    <Teleport :to="overlayHost">
      <div
        v-if="mode"
        ref="pop"
        class="canvas-pop"
        :class="width"
        role="dialog"
        tabindex="-1"
        :aria-label="mode"
        :style="{ left: at.x + 'px', top: at.y + 'px' }"
        @keydown.esc.stop="mode === 'nest' ? dontNest() : close(true)"
      >
        <CanvasElementForm
          v-if="mode === 'create'"
          :context="context"
          :into="adding.into.value"
          :draws-again="drawsAgain"
          @apply="add.created"
          @add="add.found"
          @again="add.again"
          @cancel="close(true)"
        />
        <CanvasSelectionMenu
          v-else-if="mode === 'selection'"
          :editing="editing"
          :selection="several"
          :words="words"
          @done="close(true)"
          @close="close(true)"
        />
        <CanvasBoxMenu
          v-else-if="mode === 'box' && boxAt"
          :key="boxAt.alias"
          :editing="editing"
          :box="boxAt"
          :members="members"
          @done="close(true)"
          @close="close(true)"
        />
        <CanvasLabelForm
          v-else-if="mode === 'label' && labelling"
          :title="`Label of ${labelling.sentence}`"
          :value="labelling.text"
          field="Label"
          :before="labelling.multiplicity || undefined"
          note="Drawn on this diagram only."
          optional
          @keep="keepLabel"
          @cancel="close(true)"
        />
        <CanvasLineMenu
          v-else-if="mode === 'line' && line != null"
          :editing="editing"
          :line="line"
          @edit="relation.editLine(line)"
          @done="close(true)"
          @close="close(true)"
        />
        <CanvasMenu
          v-else-if="mode === 'element' && selected"
          :heading="selected.name"
          :type="selected.type"
          :label="`${selected.name}: element`"
          :items="elementMenuItems(
            words, drafted, boxOfSelected?.name ?? null, drawsAgain,
          )"
          @choose="onElement"
          @close="close(true)"
        />
        <CanvasConnectTarget
          v-else-if="mode === 'target' && selected"
          :from="selected.name"
          :members="members.filter((m) => m.alias !== source)"
          @pick="relation.pair"
        />
        <CanvasNestTarget
          v-else-if="mode === 'nest' && selected"
          :element="selected"
          :boxes="ownBoxes.filter((box) => box.alias !== boxOfSelected?.alias)"
          :members="containersFor(selected)"
          :ask="asked"
          @box="nestIn"
          @relate="nestUnder"
          @cancel="dontNest"
        />
        <CanvasRenameForm
          v-else-if="mode === 'rename' && selected"
          :key="selected.id"
          :element="selected"
          :diagram-id="context.diagram.artifact_id"
          :drafted="drafted"
          @apply="apply"
          @cancel="close(true)"
          @failed="error = $event"
        />
        <CanvasDeleteConfirm
          v-else-if="mode === 'delete' && selected"
          :name="selected.name"
          :entity-id="selected.id"
          :words="words"
          @confirm="apply({ op: 'model.element.delete', artifact_id: selected.id })"
          @remove="onElement('remove')"
          @cancel="close(true)"
        />
        <CanvasRelationForm
          v-else-if="mode === 'relation'"
          v-model:kind="kind"
          v-model:drawing="drawing"
          v-model:src-count="srcCount"
          v-model:tgt-count="tgtCount"
          v-model:description="description"
          v-model:label="label"
          :source="nameOf(source)"
          :target="nameOf(target)"
          :options="options"
          :in-model="inModel"
          :editing="Boolean(currentLine)"
          @keep="relation.keep"
          @cancel="close(true)"
        />
        <p
          v-if="error"
          class="cp-alert"
          role="alert"
        >
          {{ error }}
        </p>
      </div>
    </Teleport>
  </div>
</template>
<style scoped src="./CanvasContentEditor.css"></style>
<style src="./canvasPopover.css"></style>
