<script setup lang="ts">
/**
 * One candidate's operations against the base chosen in *against* (06·6, F15, Q39): the same component
 * on the candidate page and on a stress analysis's Naive architecture and Adaptations tabs; *role* is
 * what its reader calls the candidate. The canvas marks the same comparison; a row selected here frames
 * its element there, and an element selected there selects its rows here (*framed*). A row's card shows
 * the element's fields, base against candidate: changed rows highlighted with the base struck through,
 * unchanged rows greyed. A comparison of several candidates reads each *fixed* to their common base: the
 * base is named, not chosen, and nothing is sketched there.
 */
import { useCan } from '../../composables/usePermissions'
import { computed, nextTick, ref, watch } from 'vue'
import { stableEntityId } from '../../../domain/artifactId'
import type { ChangeDifference } from '../../../domain/schemas/candidates'
import { chosenIds } from '../../../domain/candidates/candidateCanvas'
import { chainOf, stackLine } from '../../../domain/candidates/candidateStack'
import type { Candidates } from '../../composables/useCandidates'

const props = defineProps<{
  candidates: Candidates; role: string; nameOf: (id: string) => string; fixed?: boolean
  /** The element selected on the canvas, by stable id: its rows are selected here. */
  framed?: string | null
}>()
const emit = defineEmits<{ frame: [target: string | null]; sketch: [id: string] }>()

const summary = computed(() =>
  props.candidates.all.value.find((one) => one.id === props.candidates.selected.value) ?? null)
const comparison = computed(() => props.candidates.comparison.value)
const baseLabel = computed(() => props.candidates.choices.value
  .find((one) => one.value === props.candidates.against.value)?.label ?? props.candidates.against.value)
const onBranch = computed(() => {
  const id = summary.value?.id
  const base = props.candidates.against.value
  return !id || base === 'model' || chainOf(id, props.candidates.all.value).some((one) => one.id === base)
})

const entityFields = computed(() => new Map((comparison.value?.view.entities ?? []).map((one) => [one.id, one.fields])))
/** An element by name: as this candidate composes it, else as its reader names it. */
const nameIn = (id: string): string => {
  const named = entityFields.value.get(id)?.name
  return typeof named === 'string' ? named : props.nameOf(id)
}
const targetName = (row: ChangeDifference): string => {
  if (typeof row.target !== 'string') {
    const { source_entity: source, connection_type: type, target_entity: target } = row.target
    return `${nameIn(source)} → ${nameIn(target)} (${type.replace('archimate-', '')})`
  }
  const named = row.fields.name?.after ?? row.fields.name?.before
  return entityFields.value.has(row.target) || typeof named !== 'string' ? nameIn(row.target) : named
}
const CHANGE_WORD: Readonly<Record<string, string>> = { added: '+ added', edited: '~ changed', removed: '− removed' }
const changeWord = (row: ChangeDifference): string =>
  row.change === 'removed' && !onBranch.value ? 'only in the base' : (CHANGE_WORD[row.change] ?? row.change)
const shown = (value: unknown): string =>
  value === null || value === undefined || value === ''
    ? '—'
    : typeof value === 'string' ? value : JSON.stringify(value)

const standingOf = (row: ChangeDifference): string => {
  const target = typeof row.target === 'string' ? row.target : null
  // What the stack creates is named by its reference; the view says the id its create was given.
  const chosen = target === null ? undefined : chosenIds(comparison.value?.view ?? { entities: [] }).get(target)
  const found = comparison.value?.standing.find(({ operation }) =>
    target !== null && (operation.artifact_id === target || (chosen !== undefined && operation.artifact_id === chosen)))
  return found?.standing ?? ''
}

const selectedRow = ref<number | null>(null)
const table = ref<HTMLTableElement | null>(null)
/** Whether *row* is about the element *stableId*: the element itself, or a relation at either end. */
const about = (row: ChangeDifference, stableId: string): boolean => (typeof row.target === 'string'
  ? stableEntityId(chosenIds(comparison.value?.view ?? { entities: [] }).get(row.target) ?? row.target) === stableId
  : [row.target.source_entity, row.target.target_entity].some((end) => stableEntityId(end) === stableId))
const framedRows = computed(() => new Set((comparison.value?.diff ?? []).flatMap((row, index) =>
  (props.framed && about(row, props.framed) ? [index] : []))))
watch(framedRows, async (rows) => {
  if (!rows.size) return
  await nextTick()
  table.value?.querySelector('tr.framed')?.scrollIntoView({ block: 'nearest' })
})
const card = ref<number | null>(null)
const select = (index: number, row: ChangeDifference) => {
  selectedRow.value = selectedRow.value === index ? null : index
  emit('frame', selectedRow.value === null || typeof row.target !== 'string' ? null : row.target)
}
const cardRows = (row: ChangeDifference) => {
  const fields = typeof row.target === 'string' ? entityFields.value.get(row.target) ?? {} : {}
  const names = [...new Set([...Object.keys(row.fields), ...Object.keys(fields)])]
    .filter((name) => typeof fields[name] !== 'object' || row.fields[name])
  return names.map((name) => ({ name, changed: row.fields[name], value: fields[name] }))
}
const maySketch = useCan('changes_record_operation')
</script>

<template>
  <section
    v-if="summary"
    class="ops"
    data-testid="candidate-operations"
  >
    <div class="ops-h">
      <div>
        <b>{{ summary.name }}</b>
        <span class="role">{{ role }} · {{ summary.state }}</span>
        <span class="stack-of">{{ stackLine(summary.id, candidates.all.value) }}</span>
      </div>
      <button
        v-if="summary.state === 'draft' && !fixed"
        type="button"
        class="btn btn-sm"
        data-testid="sketch"
        :disabled="!maySketch.allowed"
        :title="maySketch.allowed ? undefined : maySketch.reason"
        @click="emit('sketch', summary.id)"
      >
        Sketch on the canvas
      </button>
    </div>
    <div class="reads">
      <span v-if="fixed">against {{ baseLabel }}</span>
      <label v-else>against
        <select
          :value="candidates.against.value"
          data-testid="against"
          @change="candidates.compareWith(($event.target as HTMLSelectElement).value)"
        >
          <option
            v-for="choice in candidates.choices.value"
            :key="choice.value"
            :value="choice.value"
          >{{ choice.label }}</option>
        </select>
      </label>
    </div>
    <p
      v-if="comparison && !comparison.diff.length"
      class="empty"
    >
      No operations against this base yet. Every change made to this candidate becomes one here.
    </p>
    <table
      v-else-if="comparison"
      ref="table"
      class="tbl"
    >
      <thead><tr><th>Artifact</th><th>Change</th><th>Base → proposed</th><th>Standing</th></tr></thead>
      <tbody>
        <tr
          v-for="(row, index) in comparison.diff"
          :key="index"
          class="oprow"
          :class="{
            sel: index === selectedRow, framed: framedRows.has(index),
            'base-only': changeWord(row) === 'only in the base',
          }"
          @click="select(index, row)"
          @mouseenter="card = index"
          @mouseleave="card = null"
        >
          <td>
            {{ targetName(row) }}
            <span class="sub">{{ row.kind }}</span>
            <div
              v-if="card === index && typeof row.target === 'string'"
              class="fcard"
              role="tooltip"
            >
              <h4>{{ targetName(row) }}</h4>
              <table>
                <tr><th>Field</th><th>Base</th><th>Candidate</th></tr>
                <tr
                  v-for="field in cardRows(row)"
                  :key="field.name"
                  :class="field.changed ? 'chg' : 'same'"
                >
                  <td>{{ field.name }}</td>
                  <td :class="{ was: field.changed }">
                    <span class="v">{{ shown(field.changed ? field.changed.before : field.value) }}</span>
                  </td>
                  <td><span class="v">{{ shown(field.changed ? field.changed.after : field.value) }}</span></td>
                </tr>
              </table>
            </div>
          </td>
          <td class="chg-word">
            {{ changeWord(row) }}
          </td>
          <td>
            <div
              v-for="(field, name) in row.fields"
              :key="name"
              class="field"
            >
              <span class="fname">{{ name }}</span>
              <s v-if="row.change !== 'added'">{{ shown(field.before) }}</s>
              <b v-if="row.change !== 'removed'">{{ shown(field.after) }}</b>
            </div>
          </td>
          <td>
            <span
              v-if="standingOf(row)"
              :class="`standing standing--${standingOf(row).replace(' ', '-')}`"
            >{{ standingOf(row) }}</span>
          </td>
        </tr>
      </tbody>
    </table>
    <p
      v-if="candidates.error.value"
      class="err"
      role="alert"
    >
      {{ candidates.error.value }}
    </p>
  </section>
</template>

<style scoped>
.ops-h { display: flex; gap: 8px; align-items: flex-start; justify-content: space-between; padding: 8px 10px 4px; }
.ops-h b { font-size: 13px; }
.role, .stack-of { display: block; font-size: 11.5px; color: var(--muted); }
.reads {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
  font-size: 12px;
}
.reads select { font-size: 12px; max-width: 260px; margin-left: 4px; }
.empty { padding: 10px; font-size: 12.5px; color: var(--muted); }
.tbl { width: 100%; border-collapse: collapse; font-size: 12.5px; }
.tbl th { text-align: left; font-size: 11px; text-transform: uppercase; color: var(--muted); padding: 4px 8px; }
.tbl td { padding: 6px 8px; border-top: 1px solid var(--border); vertical-align: top; position: relative; }
.oprow { cursor: pointer; }
.oprow.sel td, .oprow.framed td { background: var(--accent-soft); }
.oprow.framed td:first-child { box-shadow: inset 3px 0 0 var(--accent); }
.oprow.base-only td { color: var(--muted); }
.sub { display: block; font-size: 11px; color: var(--muted); }
.chg-word { white-space: nowrap; }
.field { display: flex; gap: 6px; flex-wrap: wrap; }
.fname { color: var(--muted); }
.field s { color: var(--warn-text); }
.standing { font-size: 11px; font-weight: 600; padding: 0 5px; border-radius: 3px; background: var(--soft); }
.standing--applies { background: var(--ok-soft); color: var(--ok-text); }
.standing--drifted { background: var(--warn-soft); color: var(--warn-text); }
.standing--conflicting { background: var(--danger-soft); color: var(--danger-strong); }
.fcard {
  position: absolute; left: 100%; top: 0; z-index: 40; width: 340px; background: var(--surface);
  border: 1px solid var(--border-strong);
  border-radius: 8px;
  box-shadow: var(--shadow);
  padding: 8px 10px;
  font-size: 12px;
}
.fcard h4 { font-size: 13px; margin: 0 0 6px; }
.fcard table { width: 100%; border-collapse: collapse; }
.fcard th { text-align: left; font-size: 10.5px; color: var(--faint); text-transform: uppercase; padding: 2px 4px; }
.fcard td {
  padding: 3px 4px; border-top: 1px solid var(--border); max-width: 130px; vertical-align: top;
}
.fcard .v { display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
}
.fcard tr.same td { color: var(--faint); }
.fcard tr.chg td { background: var(--warn-soft); color: var(--text); }
.fcard tr.chg td:first-child { box-shadow: inset 3px 0 0 var(--warn-text); font-weight: 600; }
.fcard .was { text-decoration: line-through; color: var(--warn-text); }
.err { color: var(--danger-strong); padding: 6px 10px; font-size: 12px; }
</style>
