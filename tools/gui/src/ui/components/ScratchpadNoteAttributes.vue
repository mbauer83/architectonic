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
 * An attribute the schema does not declare stays editable as text. It is carried into a lift as an
 * ad-hoc property, and the server's warning on the note says so.
 */
import { computed, inject, ref, watch } from 'vue'
import { Effect } from 'effect'
import TypedPropertyInput from './TypedPropertyInput.vue'
import { modelServiceKey } from '../keys'
import { attributeLevel } from '../composables/scratchpadClassification'
import { attributeCell, attributeRows } from '../composables/scratchpadAttributes'
import { without } from '../composables/scratchpadEdits'
import type { EntityAttributeDescriptor } from '../../domain'
import type { ClassificationLevel, Note } from '../../domain/schemas/scratchpads'

const props = defineProps<{
  note: Note
  levels: readonly ClassificationLevel[]
}>()
const emit = defineEmits<{
  (event: 'attribute-note', payload: { id: string; name: string; value: string }): void
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

const commit = (name: string): void => {
  const value = drafts.value[name]
  if (value === undefined) return
  drafts.value = without(drafts.value, name)
  emit('attribute-note', { id: props.note.id, name, value })
}
</script>

<template>
  <section
    v-if="subject && rows.length"
    class="attributes"
    data-testid="note-attributes"
  >
    <h3>Attributes</h3>
    <div
      v-for="row in rows"
      :key="row.name"
      class="row"
      :data-attribute="row.name"
      @change="commit(row.name)"
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
        :descriptor="descriptors[row.name] ?? { type: 'string' }"
        :required="required.has(row.name)"
        @update:model-value="drafts = { ...drafts, [row.name]: $event }"
      />
    </div>
  </section>
</template>

<style scoped>
.attributes { border-top: 1px solid #f0f0f2; margin-top: 10px; padding-top: 8px; }
.attributes h3 {
  font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: #9ca3af; margin: 0 0 6px;
}
.row { display: flex; align-items: flex-start; gap: 8px; margin-bottom: 6px; }
.name { flex: 1; color: #6b7280; padding-top: 6px; word-break: break-word; }
.name.undeclared { font-style: italic; color: #d97706; }
.required { color: #b91c1c; text-decoration: none; margin-left: 2px; }
</style>
