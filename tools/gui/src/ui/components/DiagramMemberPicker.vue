<script setup lang="ts">
/**
 * The edit panel's discovery (sketch 01·8, D15): search the model; the relations the model holds between
 * drawn elements that the diagram does not draw, each with *Draw*; and the elements one and two steps
 * away. A row that adds is dragged onto the canvas, or focused and Enter pressed; an element the diagram
 * already draws is listed "on this diagram" and selects instead. Hovering or focusing a relation's row
 * outlines its two ends on the canvas.
 *
 * Escape in the search clears its text first; the next goes on outward (Q40).
 */
import { computed, inject, ref, watch } from 'vue'
import { Effect, Exit } from 'effect'
import type { DiagramContext, EntityDisplayInfo } from '../../domain'
import {
  type Discovered, discovered, undrawnRelationsAmong, type UndrawnRelation,
} from '../../domain/layout/editDiscovery'
import { modelServiceKey } from '../keys'
import { carryEntity, type CarriedEntity } from '../lib/entityDrag'
import { connectionTypeLabel } from '../../domain/connectionTypeLabel'
import { toGlyphKey } from '../lib/glyphKey'
import ArchimateTypeGlyph from './ArchimateTypeGlyph.vue'

const props = defineProps<{
  context: DiagramContext
  busy: boolean
  /** What the session draws now, by the element's stable id, to the alias it is drawn under. */
  drawn: ReadonlyMap<string, string>
  /** The relations the session draws now, by stable id. */
  drawnRelations: ReadonlySet<string>
}>()
const emit = defineEmits<{
  add: [entity: CarriedEntity]
  draw: [relationId: string]
  select: [alias: string]
  outline: [aliases: readonly string[]]
  outward: []
}>()
const svc = inject(modelServiceKey)!

const relations = computed(() =>
  undrawnRelationsAmong(props.context.candidate_connections, props.drawn, props.drawnRelations))
const STEPS = [[1, 'One step away'], [2, 'Two steps away']] as const
const nearby = computed(() => STEPS.flatMap(([hop, heading]) => {
  const rows = discovered(props.context.suggested_entities.filter((group) => group.hop === hop)
    .flatMap((group) => group.items), props.drawn).filter((row) => row.drawnAs === undefined)
  return rows.length ? [{ hop, heading, rows }] : []
}))

const query = ref('')
const found = ref<readonly EntityDisplayInfo[]>([])
const searching = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined
watch(query, (text) => {
  clearTimeout(timer)
  if (!text.trim()) { found.value = []; return }
  timer = setTimeout(async () => {
    searching.value = true
    const exit = await Effect.runPromiseExit(svc.searchEntityDisplay({
      query: text.trim(), limit: 20, diagramType: props.context.diagram.diagram_type,
    }))
    searching.value = false
    if (query.value === text) found.value = Exit.isSuccess(exit) ? exit.value.items : []
  }, 200)
})
const results = computed(() => discovered(found.value, props.drawn))

const root = ref<HTMLElement | null>(null)
const field = ref<HTMLInputElement | null>(null)
/** ↓ and ↑ walk the rows from the field and back to it; Enter on a row is its button's. */
const walk = (event: KeyboardEvent) => {
  if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return
  const rows = [...root.value?.querySelectorAll<HTMLElement>('[data-row]') ?? []]
  const at = rows.findIndex((row) => row === document.activeElement)
  const next = event.key === 'ArrowDown' ? at + 1 : at - 1
  event.preventDefault()
  if (next < 0) field.value?.focus()
  else rows[Math.min(next, rows.length - 1)]?.focus()
}
const escape = (event: KeyboardEvent) => {
  event.stopPropagation()
  if (query.value) query.value = ''
  else { field.value?.blur(); emit('outward') }
}

const point = (relation: UndrawnRelation | null) => emit('outline', relation ? relation.ends : [])
const choose = (row: Discovered<EntityDisplayInfo>) => {
  if (row.drawnAs !== undefined) emit('select', row.drawnAs)
  else emit('add', row.entity)
}
</script>

<template>
  <section
    ref="root"
    class="card member-picker"
    aria-label="Add from model"
    @keydown="walk"
  >
    <input
      ref="field"
      v-model="query"
      type="search"
      class="mp-search"
      placeholder="Search the model"
      aria-label="Search the model"
      autocomplete="off"
      data-testid="edit-panel-search"
      @keydown.esc="escape"
    >
    <p class="mp-hint">
      Drag onto the diagram to add it — or focus a row and press Enter.
    </p>

    <template v-if="query.trim()">
      <p
        v-if="searching && !results.length"
        class="mp-none"
      >
        Searching…
      </p>
      <p
        v-else-if="!results.length"
        class="mp-none"
      >
        Nothing in the model matches.
      </p>
      <button
        v-for="row in results"
        :key="row.entity.artifact_id"
        type="button"
        data-row
        :draggable="row.drawnAs === undefined"
        :disabled="busy && row.drawnAs === undefined"
        :class="{ 'mp-drawn': row.drawnAs !== undefined }"
        :title="row.drawnAs !== undefined ? 'On this diagram: select it' : `Add ${row.entity.name} to the diagram`"
        @dragstart="carryEntity($event.dataTransfer, row.entity)"
        @click="choose(row)"
      >
        <span class="mp-grip">{{ row.drawnAs === undefined ? '⠿' : '◎' }}</span>
        <ArchimateTypeGlyph
          :type="toGlyphKey(row.entity.artifact_type)"
          :size="13"
        />
        <span class="mp-name">{{ row.entity.name }}</span>
        <small v-if="row.drawnAs !== undefined">on this diagram</small>
      </button>
    </template>

    <template v-else>
      <template v-if="relations.length">
        <h4>Relations in the model, not drawn</h4>
        <div
          v-for="relation in relations"
          :key="relation.id"
          class="mp-relation"
          data-testid="edit-panel-relation"
          @mouseenter="point(relation)"
          @mouseleave="point(null)"
          @focusin="point(relation)"
          @focusout="point(null)"
        >
          <span class="mp-sentence">{{ relation.sourceName }} — {{ connectionTypeLabel(relation.type) }} →
            {{ relation.targetName }}</span>
          <button
            type="button"
            data-row
            :disabled="busy"
            :aria-label="`Draw ${relation.sourceName} ${connectionTypeLabel(relation.type)} ${relation.targetName}`"
            @click="emit('draw', relation.id)"
          >
            Draw
          </button>
        </div>
      </template>
      <template
        v-for="group in nearby"
        :key="group.hop"
      >
        <h4>{{ group.heading }}</h4>
        <button
          v-for="row in group.rows"
          :key="row.entity.artifact_id"
          type="button"
          data-row
          draggable="true"
          :disabled="busy"
          :data-hop="group.hop"
          @dragstart="carryEntity($event.dataTransfer, row.entity)"
          @click="emit('add', row.entity)"
        >
          ⠿ {{ row.entity.name }}
        </button>
      </template>
    </template>
  </section>
</template>

<style scoped>
.member-picker { display: grid; gap: .35rem; max-height: 24rem; overflow: auto; padding: .75rem; }
.mp-search { width: 100%; box-sizing: border-box; }
h4 {
  margin: .4rem 0 0; font-size: 10.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em;
  color: var(--muted);
}
button {
  display: flex; gap: 6px; align-items: center; text-align: start; cursor: grab; padding: 3px 6px;
  border: 1px solid var(--border); border-radius: 4px; background: var(--surface); color: var(--text);
}
button:hover:not(:disabled), button:focus-visible { background: var(--hover); }
button.mp-drawn { cursor: pointer; border-style: dashed; }
.mp-grip { color: var(--faint); }
.mp-name { flex: 1; min-width: 0; }
small { color: var(--faint); font-size: 11px; }
.mp-relation {
  display: flex; gap: 6px; align-items: center; padding: 3px 4px; border-radius: 4px; font-size: .9em;
}
.mp-relation:hover, .mp-relation:focus-within { background: var(--accent-soft); }
.mp-relation button { cursor: pointer; flex: none; }
.mp-sentence { flex: 1; min-width: 0; }
.mp-hint, .mp-none { margin: 0; font-size: .85em; color: var(--muted); }
</style>
