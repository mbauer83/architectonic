<script setup lang="ts">
/**
 * A note's attributes, edited with the controls an entity's properties are edited with.
 *
 * Offered once the note has reached a classification level its meta-ontology says carries
 * attributes. From there the schema is the one the entity it would become is verified against —
 * fetched from the endpoint the entity forms use — and each attribute gets the same typed input
 * they render. Below that level nothing is offered: no schema applies yet, and attributes the note
 * already holds are left exactly as they are.
 *
 * An attribute the schema does not declare can be added, typed, and removed, as the entity form's
 * "Add property" allows. It is carried into a lift as an ad-hoc property of the type it was given,
 * and the server's warning on the note says so.
 */
import { computed, inject, ref, watch } from 'vue'
import { Effect } from 'effect'
import TypedPropertyInput from './TypedPropertyInput.vue'
import { modelServiceKey } from '../keys'
import { attributeLevel } from '../composables/scratchpadClassification'
import {
  AD_HOC_TYPES, adHocTypeOf, adHocValue, attributeCell, attributeNameProblem, attributeRows,
} from '../composables/scratchpadAttributes'
import type { AdHocType, AttributeRow } from '../composables/scratchpadAttributes'
import { without } from '../composables/scratchpadEdits'
import type { EntityAttributeDescriptor } from '../../domain'
import type { ClassificationLevel, Note } from '../../domain/schemas/scratchpads'

const props = defineProps<{
  note: Note
  levels: readonly ClassificationLevel[]
}>()
const emit = defineEmits<{
  (event: 'attribute-note', payload: { id: string; name: string; value: unknown }): void
}>()

const svc = inject(modelServiceKey)!

const level = computed(() => attributeLevel(props.note, props.levels))
/** Which schema applies: the type's own at the type, merged with the specialization's below it. */
const subject = computed(() => {
  const type = props.note['element-type']
  if (!level.value || !type) return null
  return {
    type,
    specialization: level.value.source === 'specializations' ? props.note.specialization ?? '' : '',
  }
})

const descriptors = ref<Record<string, EntityAttributeDescriptor>>({})
const declared = ref<readonly string[]>([])
const required = ref<ReadonlySet<string>>(new Set())
let requestSeq = 0

watch(
  () => [subject.value?.type, subject.value?.specialization] as const,
  ([type, specialization]) => {
    const requestId = ++requestSeq
    descriptors.value = {}
    declared.value = []
    required.value = new Set()
    if (!type) return
    void Effect.runPromise(svc.getEntitySchemata(type, specialization || undefined))
      .then((info) => {
        // A slower answer for a type the note has since moved on from must not win.
        if (requestId !== requestSeq) return
        descriptors.value = info.descriptors
        declared.value = info.properties
        required.value = new Set(info.required)
      })
      .catch(() => { /* No schema to offer; the note's own attributes below still render. */ })
  },
  { immediate: true },
)

const rows = computed(() => attributeRows(props.note.attributes ?? {}, declared.value))

/** What is being typed, held here until the control is left.
 *
 * The typed inputs report every keystroke, and every edit of the document is an undo step and a
 * save. So a value becomes an edit when its control commits it — on blur or Enter for text, at once
 * for a select or a checkbox — which is what the body field beside this does. */
const drafts = ref<Record<string, string>>({})
watch(() => props.note.id, () => { drafts.value = {} })

const typeOf = (row: AttributeRow): AdHocType => adHocTypeOf(row.value)

/** A declared attribute stores its cell; an undeclared one stores a value of the type chosen. */
const commit = (row: AttributeRow): void => {
  const cell = drafts.value[row.name]
  if (cell === undefined) return
  drafts.value = without(drafts.value, row.name)
  const value = row.declared ? cell : adHocValue(typeOf(row), cell)
  emit('attribute-note', { id: props.note.id, name: row.name, value })
}

const retype = (row: AttributeRow, type: AdHocType): void => {
  const value = adHocValue(type, type === 'boolean' ? 'false' : attributeCell(row.value))
  emit('attribute-note', { id: props.note.id, name: row.name, value })
}

/** The attribute being added: one the schema does not declare, as the entity form's
 * "Add property" offers. Declared ones need no adding — each already has its row. */
const adding = ref<{ name: string; type: AdHocType; cell: string } | null>(null)
watch(() => props.note.id, () => { adding.value = null })
const addingProblem = computed(() =>
  adding.value ? attributeNameProblem(adding.value.name, rows.value) : null)

const add = (): void => {
  const draft = adding.value
  if (!draft || addingProblem.value) return
  const value = adHocValue(draft.type, draft.cell)
  adding.value = null
  // Empty text would be no attribute at all, so there is nothing to add yet.
  if (value !== '') emit('attribute-note', { id: props.note.id, name: draft.name.trim(), value })
}
</script>

<template>
  <section
    v-if="subject"
    class="attributes"
    data-testid="note-attributes"
  >
    <h3>Attributes</h3>
    <div
      v-for="row in rows"
      :key="row.name"
      class="row"
      :data-attribute="row.name"
      @change="commit(row)"
    >
      <span
        class="name"
        :class="{ undeclared: !row.declared }"
        :title="row.declared ? undefined : 'Not declared by the schema; carried as an ad-hoc property'"
      >{{ row.name }}<abbr
        v-if="required.has(row.name)"
        class="required"
        title="Required by the schema"
      >*</abbr></span>
      <TypedPropertyInput
        :model-value="drafts[row.name] ?? attributeCell(row.value)"
        :descriptor="descriptors[row.name] ?? { type: typeOf(row) }"
        :required="required.has(row.name)"
        @update:model-value="drafts = { ...drafts, [row.name]: $event }"
      />
      <template v-if="!row.declared">
        <select
          class="type"
          title="Value type"
          :value="typeOf(row)"
          :data-attribute-type="row.name"
          @change.stop="retype(row, ($event.target as HTMLSelectElement).value as AdHocType)"
        >
          <option
            v-for="type in AD_HOC_TYPES"
            :key="type"
            :value="type"
          >
            {{ type === 'string' ? 'text' : type }}
          </option>
        </select>
        <button
          type="button"
          class="remove"
          title="Remove this attribute"
          :data-remove-attribute="row.name"
          @click="emit('attribute-note', { id: note.id, name: row.name, value: '' })"
        >
          ×
        </button>
      </template>
    </div>

    <div
      v-if="adding"
      class="row adding"
      data-testid="note-attribute-adding"
    >
      <input
        v-model="adding.name"
        class="new-name"
        placeholder="name"
        aria-label="Attribute name"
      >
      <select
        v-model="adding.type"
        class="type"
        title="Value type"
        @change="adding.cell = adding.type === 'boolean' ? 'false' : ''"
      >
        <option
          v-for="type in AD_HOC_TYPES"
          :key="type"
          :value="type"
        >
          {{ type === 'string' ? 'text' : type }}
        </option>
      </select>
      <TypedPropertyInput
        v-model="adding.cell"
        :descriptor="{ type: adding.type }"
      />
      <button
        type="button"
        class="confirm"
        :disabled="!!addingProblem"
        :title="addingProblem ?? 'Add this attribute'"
        data-testid="note-attribute-confirm"
        @click="add"
      >
        Add
      </button>
    </div>
    <button
      v-else
      type="button"
      class="add"
      data-testid="note-attribute-add"
      @click="adding = { name: '', type: 'string', cell: '' }"
    >
      + Add attribute
    </button>
  </section>
</template>

<style scoped>
.attributes { border-top: 1px solid var(--border); margin-top: 10px; padding-top: 8px; }
.attributes h3 {
  font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: var(--faint); margin: 0 0 6px;
}
.row { display: flex; align-items: flex-start; gap: 8px; margin-bottom: 6px; }
.name { flex: 1; color: var(--muted); padding-top: 6px; word-break: break-word; }
.name.undeclared { font-style: italic; color: var(--warn); }
.required { color: var(--danger-strong); text-decoration: none; margin-left: 2px; }
.type, .new-name { padding: 5px 4px; border: 1px solid var(--border-strong); border-radius: 5px; font-size: 11.5px; }
.new-name { flex: 1; min-width: 0; }
.remove, .add, .confirm {
  border: 1px solid var(--border-strong); border-radius: 5px; background: var(--surface); color: var(--text-2);
  font-size: 11.5px; cursor: pointer; padding: 4px 8px;
}
.remove { border: none; color: var(--faint); font-size: 15px; padding: 2px 4px; }
.remove:hover { color: var(--danger); }
.confirm:disabled { opacity: .5; cursor: not-allowed; }
.adding { flex-wrap: wrap; }
</style>
