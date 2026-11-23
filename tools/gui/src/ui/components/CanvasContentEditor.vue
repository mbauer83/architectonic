<script setup lang="ts">
import { computed, inject, nextTick, ref } from 'vue'
import { Effect } from 'effect'
import type { DiagramContext } from '../../domain'
import { canvasMembers } from '../../domain/layout/canvasComposition'
import { connectionId, stableConnectionId } from '../../domain/artifactId'
import { modelServiceKey } from '../keys'
import type { DiagramEditing } from '../composables/useDiagramEditing'
import type { CanvasCommand } from '../../ports/diagramWriteBodies'
import { elementAt, useContentGestures } from '../composables/useContentGestures'
import CanvasElementForm from './CanvasElementForm.vue'
import { type CanvasWords, DIAGRAM_WORDS } from './canvasWords'

const props = defineProps<{
  editing: DiagramEditing
  context: DiagramContext
  selection?: string | null
  /** What deleting means here; the diagram page's words when absent. */
  words?: CanvasWords
}>()
const words = computed(() => props.words ?? DIAGRAM_WORDS)
const svc = inject(modelServiceKey)!
const host = ref<HTMLElement | null>(null)
const field = ref<HTMLInputElement | null>(null)
const mode = ref<'create' | 'element' | 'rename' | 'delete' | 'target' | 'relation' | null>(null)
const at = ref({ x: 0, y: 0 })
const source = ref('')
const target = ref('')
const name = ref('')
const usages = ref<number | null>(null)
const options = ref<readonly string[]>([])
const kind = ref('')
const label = ref('')
const srcCount = ref('')
const tgtCount = ref('')
const description = ref('')
const error = ref('')
const currentLine = ref('')
const members = computed(() => canvasMembers(
  props.context, props.editing.session.state.value, props.editing.session.geometry.value,
))
const selected = computed(() => members.value.find((e) => e.alias === source.value))
function position(x: number, y: number) {
  at.value = {
    x: Math.max(4, Math.min(x, window.innerWidth - 300)),
    y: Math.max(4, Math.min(y, window.innerHeight - 355)),
  }
  error.value = ''
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
  source.value = elementAt(event)?.dataset.alias ?? ''
  mode.value = selected.value ? 'element' : 'create'
}
async function rename(alias: string) {
  source.value = alias
  const el = selected.value
  if (!el) return
  name.value = el.name
  usages.value = null
  mode.value = 'rename'
  await nextTick()
  field.value?.select()
  if (
    props.editing.session.state.value?.commands?.some(
      (c) => c.op === 'model.element.create' && c.artifact_id === el.id,
    )
  ) {
    usages.value = 0
    return
  }
  try {
    const entity = await Effect.runPromise(svc.getEntity(el.id))
    if (selected.value?.id === el.id)
      usages.value = entity.referenced_in_diagrams.filter(
        (d) => d.artifact_id !== props.context.diagram.artifact_id,
      ).length
  } catch (e) {
    error.value = String(e)
  }
}
async function apply(c: CanvasCommand, overlay?: Record<string, unknown>) {
  if (await props.editing.propose(c, overlay)) mode.value = null
  else error.value = props.editing.error.value ?? 'The drawing has changed. Try again.'
}
async function pair(alias: string) {
  const from = selected.value
  const to = members.value.find((e) => e.alias === alias)
  if (!from || !to) return
  target.value = alias
  options.value = []
  kind.value = ''
  label.value = ''
  description.value = ''
  srcCount.value = ''
  tgtCount.value = ''
  currentLine.value = ''
  mode.value = 'relation'
  try {
    const permitted = await Effect.runPromise(svc.getOntologyPair(from.type, to.type))
    if (target.value !== alias || source.value !== from.alias) return
    options.value = [...new Set([...permitted.connection_types, ...permitted.symmetric])]
    kind.value = options.value[0] ?? ''
  } catch (e) {
    error.value = String(e)
  }
}
function saveRelation() {
  const from = selected.value
  const to = members.value.find((e) => e.alias === target.value)
  if (!from || !to || !kind.value) return
  const id = currentLine.value || connectionId(from.id, kind.value, to.id)
  void apply(
    {
      op: currentLine.value ? 'model.relation.edit' : 'model.relation.create',
      artifact_id: id,
      description: description.value,
      src_multiplicity: srcCount.value,
      tgt_multiplicity: tgtCount.value,
    },
    { artifact_id: id, label: label.value, include_multiplicity: true, include_description: true },
  )
}
function editLine(index: number) {
  const row = props.editing.session.geometry.value?.relations.find((r) => r.index === index)
  if (!row) return
  const record = props.context.connections.find((c) => c.edge_key === row.key)
  if (!record) return
  source.value = row.source
  target.value = row.target
  currentLine.value = record.artifact_id
  options.value = [record.conn_type]
  kind.value = record.conn_type
  const pending = props.editing.session.state.value
  const prior = props.context.diagram.extra?.connections
  const overlays = [...(Array.isArray(prior) ? prior : []), ...(pending?.overlays ?? [])]
  const overlay = overlays.reverse().find(r => stableConnectionId(String(r.artifact_id ?? r.connection_id)) === row.key)
  label.value = String(overlay?.label ?? record.edge_label_override ?? '')
  description.value = record.content_text
  srcCount.value = record.src_multiplicity ?? ''
  tgtCount.value = record.tgt_multiplicity ?? ''
  const edit = pending?.commands?.find(c => c.artifact_id === record.artifact_id && c.op === 'model.relation.edit')
  if (edit && 'src_multiplicity' in edit) {
    description.value = edit.description
    srcCount.value = edit.src_multiplicity
    tgtCount.value = edit.tgt_multiplicity
  }
  mode.value = 'relation'
}
const { touchedLine, focusCanvas, up, release, moving } = useContentGestures(
  host, props.editing, source, position, rename, editLine, pair,
)
function key(e: KeyboardEvent) {
  if (e.key === 'Escape' && mode.value) {
    e.stopPropagation()
    mode.value = null
  }
  if (e.key === 'F2' && props.selection) {
    e.preventDefault()
    const el = host.value
      ?.querySelector(`[data-alias="${CSS.escape(props.selection)}"]`)
      ?.getBoundingClientRect()
    if (el) position(el.left, el.top)
    void rename(props.selection)
  }
}
function double(e: MouseEvent) {
  position(e.clientX, e.clientY)
  const line = (e.target as Element).closest<SVGElement>('[data-relation]')
  if (line) editLine(Number(line.dataset.relation))
  else {
    const alias = elementAt(e)?.dataset.alias
    if (alias) void rename(alias)
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
    <button
      v-if="touchedLine !== null"
      type="button"
      @click="editLine(touchedLine)"
    >
      Edit selected relationship
    </button>
    <Teleport to="body">
      <div
        v-if="mode"
        class="canvas-pop"
        role="dialog"
        :aria-label="mode"
        :style="{ left: at.x + 'px', top: at.y + 'px' }"
        @keydown.esc.stop="mode = null"
      >
        <button
          type="button"
          class="close"
          aria-label="Close"
          @click="mode = null"
        >
          ×
        </button>
        <CanvasElementForm
          v-if="mode === 'create'"
          :context="context"
          @apply="apply"
        />
        <template v-else-if="mode === 'element'">
          <strong>{{ selected?.name }}</strong> <button @click="rename(source)">
            Rename
          </button><button @click="mode = 'target'">
            Connect to…
          </button>
          <button
            v-if="words.removeEntry"
            @click="editing.remove(source); mode = null"
          >
            {{ words.removeEntry }}
          </button>
          <button @click="mode = 'delete'">
            {{ words.deleteEntry }}
          </button>
        </template>
        <template v-else-if="mode === 'target'">
          <strong>Connect to…</strong>
          <button
            v-for="m in members.filter((m) => m.alias !== source)"
            :key="m.alias"
            @click="pair(m.alias)"
          >
            {{ m.name }}
          </button>
        </template>
        <form
          v-else-if="mode === 'rename' && selected"
          @submit.prevent="
            apply({ op: 'model.element.rename', artifact_id: selected.id, name: name.trim() })
          "
        >
          <label>Name <input
            ref="field"
            v-model="name"
            required
            autofocus
          ></label>
          <p v-if="usages !== null">
            {{ usages ? 'Also renamed on ' + usages + ' other diagrams' : 'No other diagram draws it' }}
          </p>
          <button type="submit">
            Keep rename
          </button>
        </form>
        <template v-else-if="mode === 'delete' && selected">
          <p>{{ words.deleteQuestion(selected.name) }}</p>
          <button @click="apply({ op: 'model.element.delete', artifact_id: selected.id })">
            {{ words.deleteConfirm }}
          </button>
        </template>
        <form
          v-else-if="mode === 'relation'"
          @submit.prevent="saveRelation"
        >
          <label>Relationship
            <select v-model="kind">
              <option
                v-for="k in options"
                :key="k"
              >{{ k }}</option>
            </select></label>
          <label>Source cardinality <input v-model="srcCount"></label>
          <label>Target cardinality <input v-model="tgtCount"></label>
          <label>Description <input v-model="description"></label>
          <label>Diagram label <input v-model="label"></label>
          <button
            :disabled="!kind"
            type="submit"
          >
            Keep relationship
          </button>
        </form>
        <p
          v-if="error"
          role="alert"
        >
          {{ error }}
        </p>
      </div>
    </Teleport>
  </div>
</template>
<style scoped>
.canvas-pop {
  position: fixed;
  z-index: 100;
  padding: 0.8rem;
  width: 286px;
  max-height: min(350px, 90vh);
  overflow: auto;
  background: var(--surface);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 6px;
  box-shadow: 0 5px 20px #0003;
}
.canvas-pop label,
.canvas-pop button,
.canvas-pop input,
.canvas-pop select {
  display: block;
  margin-block: 0.25rem;
}
.close {
  float: right;
}
.content-canvas :deep(.lab-line path),
.content-canvas :deep(.lab-line-label text) {
  pointer-events: visiblePainted;
  cursor: pointer;
}
</style>
