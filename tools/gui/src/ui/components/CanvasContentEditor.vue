<script setup lang="ts">
import { computed, inject, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import type { DiagramContext, EntityDisplayInfo } from '../../domain'
import { canvasMembers } from '../../domain/layout/canvasComposition'
import { modelServiceKey } from '../keys'
import type { DiagramEditing } from '../composables/useDiagramEditing'
import type { CanvasCommand } from '../../ports/diagramWriteBodies'
import { elementAt, useContentGestures } from '../composables/useContentGestures'
import { useCanvasPopover } from '../composables/useCanvasPopover'
import { useCanvasRelation } from '../composables/useCanvasRelation'
import { useCanvasNesting } from '../composables/useCanvasNesting'
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
import { isArchimateDiagramType } from '../lib/archimateOccurrences'
import { asksForTheMenu, isOnALine, selectedLineMiddle } from './lineMenuPlace'
import { type CanvasWords, DIAGRAM_WORDS } from './canvasWords'

const props = defineProps<{
  editing: DiagramEditing
  context: DiagramContext
  selection?: string | null
  /** The line selected on the canvas, by its place on the picture: its menu is the line's. */
  line?: number | null
  /** Every shape selected: two or more open the selection's menu rather than an element's. */
  selectedShapes?: readonly string[]
  /** What deleting means here; the diagram page's words when absent. */
  words?: CanvasWords
}>()
const words = computed(() => props.words ?? DIAGRAM_WORDS)
const several = computed(() => props.selectedShapes ?? [])
const svc = inject(modelServiceKey)!
const router = useRouter()
const host = ref<HTMLElement | null>(null)
const pop = ref<HTMLElement | null>(null)
const { mode, at, error, width, position, close } = useCanvasPopover(host, pop)
const source = ref('')
const target = ref('')
const members = computed(() => canvasMembers(
  props.context, props.editing.session.state.value, props.editing.session.geometry.value,
))
const selected = computed(() => members.value.find((e) => e.alias === source.value))
const nameOf = (alias: string) => members.value.find((e) => e.alias === alias)?.name ?? alias
const drafted = computed(() => props.editing.session.state.value?.commands?.some(
  (c) => c.op === 'model.element.create' && c.artifact_id === selected.value?.id) ?? false)

async function apply(c: CanvasCommand, overlay?: Record<string, unknown>) {
  if (await props.editing.propose(c, overlay)) close(true)
  else error.value = props.editing.error.value ?? 'The drawing has changed. Try again.'
}
const relation = useCanvasRelation(
  svc, props.editing, () => props.context, members, { source, target },
  () => { mode.value = 'relation' }, (message) => { error.value = message }, (c, overlay) => void apply(c, overlay),
)
const { kind, label, srcCount, tgtCount, description, options, currentLine } = relation
const { anchor, drawAgain, ownBoxes, boxOfSelected, nestIn, nestUnder, asked, dropped } = useCanvasNesting(
  props.editing, host, source, members, { mode, error, position, close }, (c) => void apply(c),
)

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
const addFound = (entity: EntityDisplayInfo) => {
  void props.editing.add(entity.artifact_id, entity.name, entity.artifact_type)
  close(true)
}
const dropMember = (event: DragEvent) => {
  const id = event.dataTransfer?.getData('application/x-architectonic-entity')
  const member = props.context.suggested_entities.flatMap(group => group.items)
    .find(item => item.artifact_id === id)
  if (member) void props.editing.add(member.artifact_id, member.name)
}
function menu(event: MouseEvent) {
  event.preventDefault()
  position(event.clientX, event.clientY)
  anchor.value = { x: event.clientX, y: event.clientY }
  source.value = elementAt(event)?.dataset.alias ?? ''
  if (props.line != null && isOnALine(event.target)) {
    mode.value = 'line'
    return
  }
  const onSelection = several.value.length > 1 && (!source.value || several.value.includes(source.value))
  mode.value = onSelection ? 'selection' : selected.value ? 'element' : 'create'
}
// A line's menu belongs to the line it was opened on: another line picked, or none, closes it.
watch(() => props.line, () => { if (mode.value === 'line') close() })
const { focusCanvas, up, release, moving } = useContentGestures(
  host, props.editing, source, position, rename, relation.editLine, (alias) => void relation.pair(alias), dropped,
)
const cornerOf = (alias: string) =>
  host.value?.querySelector(`[data-alias="${CSS.escape(alias)}"]`)?.getBoundingClientRect()
function key(e: KeyboardEvent) {
  if (e.key === 'Escape' && mode.value) {
    e.stopPropagation()
    close(true)
  }
  // The menu key, or Shift+F10: a selected line's menu at its middle (02·9, Q35), else the selection's.
  if (asksForTheMenu(e) && props.line != null) {
    e.preventDefault()
    const middle = selectedLineMiddle(host.value) ?? { x: 40, y: 40 }
    position(middle.x, middle.y)
    mode.value = 'line'
  } else if (asksForTheMenu(e) && props.selection) {
    e.preventDefault()
    const box = cornerOf(props.selection)
    position(box?.right ?? 40, box?.top ?? 40)
    source.value = props.selection
    mode.value = several.value.length > 1 ? 'selection' : 'element'
  }
  if (e.key === 'F2' && props.selection) {
    e.preventDefault()
    const box = cornerOf(props.selection)
    if (box) position(box.left, box.top)
    rename(props.selection)
  }
}
function double(e: MouseEvent) {
  position(e.clientX, e.clientY)
  // A double press on a label opens its relation; on a line it adds a bend, which the canvas does.
  const line = (e.target as Element).closest<SVGElement>('.lab-line-label[data-relation]')
  if (line) relation.editLine(Number(line.dataset.relation))
  else if (!(e.target as Element).closest('[data-relation], .lab-line-handles')) {
    const alias = elementAt(e)?.dataset.alias
    if (alias) rename(alias)
  }
}
</script>
<template>
  <div
    ref="host"
    class="content-canvas"
    tabindex="0"
    @keydown="key"
    @dragover.prevent
    @drop.prevent="dropMember"
    @contextmenu="menu"
    @dblclick="double"
    @pointerdown.capture="focusCanvas"
    @pointerup.capture="up"
    @pointercancel="release"
    @pointermove="moving"
  >
    <slot />
    <p
      class="live"
      aria-live="polite"
      data-testid="selection-announcement"
    >
      {{ several.length > 1 ? `${several.length} items selected` : '' }}
    </p>
    <CanvasDetailsDialog
      v-if="details"
      :key="details"
      :artifact-id="details"
      :pending="editing.session.state.value?.commands ?? []"
      :keep="keepDetails"
      @close="details = null; host?.focus({ preventScroll: true })"
    />
    <Teleport to="body">
      <div
        v-if="mode"
        ref="pop"
        class="canvas-pop"
        :class="width"
        role="dialog"
        tabindex="-1"
        :aria-label="mode"
        :style="{ left: at.x + 'px', top: at.y + 'px' }"
        @keydown.esc.stop="close(true)"
      >
        <CanvasElementForm
          v-if="mode === 'create'"
          :context="context"
          @apply="apply"
          @add="addFound"
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
          :items="elementMenuItems(words, drafted, boxOfSelected?.name ?? null, isArchimateDiagramType(context.diagram.diagram_type))"
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
          @cancel="close(true)"
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
          :words="words"
          @confirm="apply({ op: 'model.element.delete', artifact_id: selected.id })"
          @remove="onElement('remove')"
          @cancel="close(true)"
        />
        <CanvasRelationForm
          v-else-if="mode === 'relation'"
          v-model:kind="kind"
          v-model:src-count="srcCount"
          v-model:tgt-count="tgtCount"
          v-model:description="description"
          v-model:label="label"
          :title="`${nameOf(source)} → ${nameOf(target)}`"
          :options="options"
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
