<script setup lang="ts">
/**
 * What to add at a point on a diagram (sketch 03·1–2): one field that searches the model first — a
 * hit is added to the diagram — and, below it, every element type the diagram type accepts, recently
 * used first, then those already drawn, then each layer; choosing a type creates a new element of it,
 * named with what was typed. The field is focused on opening; Down walks from it into the hits and the
 * types, Up walks back, Home and End go to the ends, and a letter typed on a type goes to the filter.
 */
import { computed, inject, nextTick, onMounted, ref, watch } from 'vue'
import { Effect, Exit } from 'effect'
import { modelServiceKey } from '../keys'
import type { DiagramContext, EntityDisplayInfo } from '../../domain'
import { stableEntityId } from '../../domain/artifactId'
import ArchimateTypeGlyph from './ArchimateTypeGlyph.vue'
import { toGlyphKey } from '../lib/glyphKey'
import { domainStyle, getDomainLabel } from '../lib/domains'
import { type TypeRow, recentTypes, typeSections, typeWords } from './canvasTypeList'
import { menuStep } from './canvasMenu'
import { type ReceivingBox, admitsType } from '../../domain/layout/receivingBox'
import { partsTypes } from './canvasParts'

const props = defineProps<{
  context: DiagramContext
  /** The box under the point the menu was opened at, which the new element joins; null on open paper. */
  into?: ReceivingBox | null
  /** The diagram type draws an element more than once, so one already drawn may be drawn again. */
  drawsAgain?: boolean
}>()
const emit = defineEmits<{
  add: [entity: EntityDisplayInfo]; again: [entity: EntityDisplayInfo]; create: [type: string, name: string]
}>()
const svc = inject(modelServiceKey)!

const query = ref('')
const filter = ref('')
const hits = ref<readonly EntityDisplayInfo[]>([])
const accepted = ref<readonly TypeRow[]>([])
/** What a container may hold, as the ontology answers it; null until it has, or where the box is no container. */
const parts = ref<ReadonlySet<string> | null>(null)
/** The types the diagram type accepts that the box under the point admits: all of them on open paper. */
const palette = computed(() => accepted.value.filter((row) =>
  !props.into || admitsType(props.into.admits, row.type, row.domain, parts.value ?? undefined)))
const error = ref('')
const root = ref<HTMLElement | null>(null)
const search = ref<HTMLInputElement | null>(null)
const filterField = ref<HTMLInputElement | null>(null)
const recent = recentTypes()

const drawn = computed(() => new Set(props.context.entities.map((one) => stableEntityId(one.artifact_id))))
const onDiagram = (hit: EntityDisplayInfo) => drawn.value.has(stableEntityId(hit.artifact_id))
const sections = computed(() =>
  typeSections(palette.value, props.context.entities.map((one) => one.artifact_type), recent, filter.value))

onMounted(async () => {
  await nextTick()
  search.value?.focus()
  try {
    const diagramType = props.context.diagram.diagram_type
    const rows = await Effect.runPromise(svc.listDiagramElementTypes(diagramType))
    accepted.value = rows.map((row) => ({ type: String(row.artifact_type), domain: String(row.domain) }))
    const admits = props.into?.admits
    if (admits?.kind === 'parts') parts.value = await partsTypes(svc, diagramType, admits.containerType)
  } catch (e) {
    error.value = String(e)
  }
})

let timer: ReturnType<typeof setTimeout> | undefined
const find = async (text: string) => {
  const exit = await Effect.runPromiseExit(svc.searchEntityDisplay({
    query: text.trim(), limit: 6, diagramType: props.context.diagram.diagram_type,
  }))
  if (query.value === text && Exit.isSuccess(exit)) hits.value = exit.value.items.filter((one) => !one.diagram_internal)
}
watch(query, (text) => {
  clearTimeout(timer)
  if (!text.trim()) {
    hits.value = []
    return
  }
  timer = setTimeout(() => void find(text), 200)
})

const choose = (hit: EntityDisplayInfo) => {
  if (!onDiagram(hit)) emit('add', hit)
  else if (props.drawsAgain) emit('again', hit)
}
/** What choosing a hit already drawn does, or that it does nothing: said under its name (03·1). */
const drawnHint = computed(() =>
  (props.drawsAgain ? 'on this diagram — adds a second occurrence' : 'already on this diagram'))

const options = () => [...root.value?.querySelectorAll<HTMLElement>('[role="option"]') ?? []]
const walk = (event: KeyboardEvent) => {
  const all = options()
  const at = all.indexOf(document.activeElement as HTMLElement)
  const field = event.target === search.value || event.target === filterField.value
  if (field && (event.key === 'Home' || event.key === 'End' || event.key === 'ArrowUp')) return
  if (event.key === 'ArrowDown' && event.target === filterField.value) {
    event.preventDefault()
    root.value?.querySelector<HTMLElement>('.picker__types [role="option"]')?.focus()
    return
  }
  if (event.key === 'ArrowUp' && at === 0) {
    event.preventDefault()
    search.value?.focus()
    return
  }
  const next = menuStep(event.key, at, all.length)
  if (next !== null) {
    event.preventDefault()
    all[next]?.focus()
  } else if (event.key === 'Enter' && event.target === filterField.value) {
    event.preventDefault()
    root.value?.querySelector<HTMLElement>('.picker__types [role="option"]')?.click()
  } else if ((event.key === 'Enter' || event.key === ' ') && at >= 0) {
    event.preventDefault()
    all[at]?.click()
  } else if (at >= 0 && event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey
    && all[at]?.dataset.type) {
    event.preventDefault()
    filter.value += event.key
    filterField.value?.focus()
  }
}
</script>

<template>
  <div
    ref="root"
    class="picker"
    @keydown="walk"
  >
    <p
      class="picker__meta"
      data-testid="picker-heading"
    >
      {{ into ? `Add to ${into.label}` : 'Add here' }}
    </p>
    <input
      ref="search"
      v-model="query"
      class="cp-input"
      type="search"
      autocomplete="off"
      aria-label="Search the model, or name something new"
      placeholder="Search the model, or name something new…"
    >
    <template v-if="query.trim()">
      <p class="picker__meta">
        In the model
      </p>
      <div
        v-if="hits.length"
        role="listbox"
        aria-label="In the model"
      >
        <div
          v-for="hit in hits"
          :key="hit.artifact_id"
          class="picker__opt"
          role="option"
          tabindex="-1"
          :aria-disabled="onDiagram(hit) && !drawsAgain ? 'true' : undefined"
          :aria-selected="false"
          @click="choose(hit)"
        >
          <ArchimateTypeGlyph
            :type="toGlyphKey(hit.artifact_type)"
            :size="16"
          />
          <span class="picker__grow">
            {{ hit.name }}
            <span class="picker__hint">{{ typeWords(hit.artifact_type) }}{{
              onDiagram(hit) ? ` · ${drawnHint}` : '' }}</span>
          </span>
        </div>
      </div>
      <p
        v-else
        class="picker__none"
      >
        Nothing in the model is called that.
      </p>
      <p class="picker__create">
        Create “{{ query.trim() }}” as…
        <span class="picker__hint">a new element; choose its type below</span>
      </p>
    </template>
    <p class="picker__meta picker__meta--rule">
      Or create a new element of type
    </p>
    <input
      ref="filterField"
      v-model="filter"
      class="cp-input"
      autocomplete="off"
      aria-label="Filter element types"
      placeholder="Filter types…"
    >
    <div
      class="picker__types"
      role="listbox"
      aria-label="Element types"
    >
      <div
        v-for="section in sections"
        :key="section.key"
        role="group"
        :aria-label="section.title"
      >
        <p
          v-if="section.framework"
          class="picker__framework"
        >
          {{ section.framework }}
        </p>
        <p class="picker__group">
          <span
            v-if="section.domain"
            class="picker__dot"
            :style="domainStyle(section.domain)"
          />{{ section.title }}<small v-if="section.note">{{ section.note }}</small>
        </p>
        <div
          v-for="row in section.items"
          :key="row.type"
          class="picker__opt"
          role="option"
          tabindex="-1"
          :aria-selected="false"
          :data-type="row.type"
          @click="emit('create', row.type, query.trim())"
        >
          <ArchimateTypeGlyph
            :type="toGlyphKey(row.type)"
            :size="16"
          />
          <span class="picker__grow">{{ typeWords(row.type) }}</span>
          <small class="picker__layer"><span
            class="picker__dot"
            :style="domainStyle(row.domain)"
          />{{ getDomainLabel(row.domain).toLowerCase() }}</small>
        </div>
      </div>
      <p
        v-if="palette.length && !sections.length"
        class="picker__none"
      >
        No element type is called that.
      </p>
    </div>
    <p class="picker__foot">
      {{ palette.length === accepted.length ? `All ${accepted.length} types this diagram type accepts.`
        : `${palette.length} of ${accepted.length} types: those ${into?.label} takes.` }}
    </p>
    <p
      v-if="error"
      class="cp-alert"
      role="alert"
    >
      {{ error }}
    </p>
  </div>
</template>

<style scoped>
.picker { display: flex; flex-direction: column; gap: 2px; padding: 0 4px 2px; }
.picker__meta {
  margin: 4px 2px 4px; font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: var(--faint);
}
.picker__meta--rule { border-top: 1px solid var(--hair); padding-top: 8px; margin-top: 8px; }
.picker__types {
  max-height: 260px; overflow-y: auto; overscroll-behavior: contain; border-top: 1px solid var(--hair);
  margin-top: 4px; position: relative;
}
.picker__framework {
  position: sticky; top: 0; z-index: 2; background: var(--surface); margin: 4px 0 0; padding: 8px 6px 0;
  font-size: 10.5px; letter-spacing: .04em; text-transform: uppercase; color: var(--faint);
  border-top: 1px solid var(--hair);
}
.picker__group {
  position: sticky; top: 0; z-index: 1; background: var(--surface); margin: 0; padding: 6px 6px 2px;
  display: flex; gap: 6px; align-items: center; font-size: 11px; font-weight: 600; color: var(--muted);
}
.picker__group small { font-weight: 400; color: var(--faint); }
.picker__dot {
  display: inline-block; flex: none; width: 8px; height: 8px; border-radius: 50%; background: var(--domain);
  border: 1px solid var(--border-strong);
}
.picker__opt {
  display: flex; gap: 8px; align-items: center; padding: 4px 8px; border-radius: 4px; cursor: pointer;
  font-size: 12.5px; color: var(--text);
}
.picker__opt :deep(svg) { flex: none; color: var(--text-2); }
.picker__opt:hover, .picker__opt:focus { background: var(--accent-soft); outline: none; }
.picker__opt[aria-disabled="true"] { color: var(--faint); cursor: default; }
.picker__opt[aria-disabled="true"]:hover { background: none; }
.picker__grow { flex: 1; min-width: 0; }
.picker__hint { display: block; color: var(--faint); font-size: 11px; }
.picker__layer { display: inline-flex; gap: 4px; align-items: center; color: var(--faint); font-size: 11px; }
.picker__create { margin: 4px 0 0; padding: 6px 8px 2px; border-top: 1px solid var(--hair); font-size: 12.5px; }
.picker__none, .picker__foot { margin: 4px 6px; color: var(--faint); font-size: 11px; }
</style>
