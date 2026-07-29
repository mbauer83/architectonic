<script setup lang="ts">
import { computed } from 'vue'
import ActivityEntityPicker from '../activity/ActivityEntityPicker.vue'
import type { Attribute, Classifier, ClassifierKind, UniqueKey } from './useDatatypeModel'
import { CLASSIFIER_KINDS } from './useDatatypeModel'
import type { CatalogClassifier } from './ClassifierCard.helpers'
import { buildTypeOptions } from './ClassifierCard.helpers'
import AttributeRow from './AttributeRow.vue'
import KeysSection from './KeysSection.vue'
import ClassifierMetadata from './ClassifierMetadata.vue'
import DatatypeNoteSection from './DatatypeNoteSection.vue'

const props = defineProps<{
  classifier: Classifier
  primitiveTypes: readonly string[]
  classifiers: readonly Classifier[]
  catalogClassifiers: readonly CatalogClassifier[]
  diagramId: string
  usageCount: number
}>()
const emit = defineEmits<{
  update: [patch: Partial<Classifier>]
  remove: []
  addAttr: []
  removeAttr: [index: number]
  updateAttr: [index: number, patch: Partial<Attribute>]
  addLiteral: []
  removeLiteral: [index: number]
  updateLiteral: [index: number, value: string]
  newClassifier: [attrIndex: number]
}>()

const isEnum = computed(() => props.classifier.classifier_kind === 'enumeration')
const attributes = computed(() => props.classifier.attributes ?? [])
const roleRequired = computed(() =>
  !isEnum.value && (attributes.value.length > 0 || !!props.classifier.is_abstract),
)

const typeOptions = computed(() => buildTypeOptions(
  props.primitiveTypes,
  props.classifiers,
  props.catalogClassifiers,
  props.diagramId,
))

const onKindChange = (e: Event) => {
  const kind = (e.target as HTMLSelectElement).value as ClassifierKind
  const patch: Partial<Classifier> = { classifier_kind: kind }
  if (kind === 'enumeration') patch.attributes = undefined
  else patch.literals = undefined
  emit('update', patch)
}
</script>

<template>
  <div class="cls-card">
    <section class="card-section">
      <div class="section-row">
        <span class="section-title">Identity</span>
        <span
          class="usage-count"
          :title="`${usageCount} attribute type usage${usageCount === 1 ? '' : 's'}`"
        >
          {{ usageCount }} usages
        </span>
      </div>
      <div class="cls-hdr">
        <select
          class="kind-sel"
          title="Classifier kind"
          :value="classifier.classifier_kind"
          @change="onKindChange"
        >
          <option
            v-for="k in CLASSIFIER_KINDS"
            :key="k"
            :value="k"
          >
            {{ k }}
          </option>
        </select>
        <input
          class="label-in"
          type="text"
          :value="classifier.label ?? ''"
          placeholder="Classifier name"
          @input="emit('update', { label: ($event.target as HTMLInputElement).value || undefined })"
        >
        <label
          class="abstract-chk"
          title="Abstract — the general end of a sum type"
        >
          <input
            type="checkbox"
            :checked="!!classifier.is_abstract"
            @change="emit('update', { is_abstract: ($event.target as HTMLInputElement).checked || undefined })"
          > abstract
        </label>
        <button
          class="del-btn"
          type="button"
          title="Remove classifier"
          @click="emit('remove')"
        >
          ×
        </button>
      </div>
      <div class="dob-row">
        <span class="field-label">Data Object binding</span>
        <ActivityEntityPicker
          :entity-id="classifier.entity_id"
          :accepted-types="['data-object']"
          @pick="(id) => emit('update', { entity_id: id ?? undefined })"
        />
      </div>
    </section>

    <template v-if="!isEnum">
      <section class="card-section attrs-section">
        <div class="section-row">
          <span class="section-title">Attributes</span>
          <button
            class="add-btn"
            type="button"
            @click="emit('addAttr')"
          >
            + Attribute
          </button>
        </div>
        <AttributeRow
          v-for="(attr, i) in attributes"
          :key="attr.id || i"
          :attr="attr"
          :type-options="typeOptions"
          @update="(patch) => emit('updateAttr', i, patch)"
          @remove="emit('removeAttr', i)"
          @new-classifier="emit('newClassifier', i)"
        />
      </section>
      <section class="card-section">
        <KeysSection
          :attributes="attributes"
          :identity="classifier.identity"
          :unique-keys="classifier.unique_keys"
          @update-identity="emit('update', { identity: $event })"
          @update-unique-keys="(keys: UniqueKey[] | undefined) => emit('update', { unique_keys: keys })"
        />
      </section>
      <section class="card-section">
        <ClassifierMetadata
          :classifier="classifier"
          :role-required="roleRequired"
          @update="emit('update', $event)"
        />
      </section>
    </template>

    <template v-else>
      <section class="card-section lits-section">
        <div class="section-row">
          <span class="section-title">Literals</span>
          <button
            class="add-btn"
            type="button"
            @click="emit('addLiteral')"
          >
            + Literal
          </button>
        </div>
        <div
          v-for="(lit, i) in classifier.literals ?? []"
          :key="i"
          class="lit-row"
        >
          <input
            type="text"
            class="lit-in"
            :value="lit"
            @input="emit('updateLiteral', i, ($event.target as HTMLInputElement).value)"
          >
          <button
            class="del-btn"
            type="button"
            @click="emit('removeLiteral', i)"
          >
            ×
          </button>
        </div>
      </section>
    </template>
    <section class="card-section">
      <span class="section-title">Notes</span>
      <DatatypeNoteSection
        :note="classifier.note"
        @update="emit('update', { note: $event })"
      />
    </section>
  </div>
</template>

<style scoped>
.cls-card { border: 1px solid #e2e8f0; border-radius: 6px; padding: 8px; background: #fff; display: flex; flex-direction: column; gap: 6px; }
.card-section { display: flex; flex-direction: column; gap: 5px; padding-top: 6px; border-top: 1px solid #f1f5f9; }
.card-section:first-child { padding-top: 0; border-top: 0; }
.cls-hdr { display: flex; gap: 4px; align-items: center; }
.usage-count { margin-left: auto; font-size: 10px; color: #6b7280; white-space: nowrap; }
.kind-sel { font-size: 11px; border: 1px solid #cbd5e1; border-radius: 4px; padding: 2px 4px; background: #f1f5f9; }
.label-in { flex: 1; font-size: 12px; border: 1px solid #cbd5e1; border-radius: 4px; padding: 2px 6px; }
.abstract-chk { font-size: 10px; color: #6b7280; display: flex; align-items: center; gap: 2px; cursor: pointer; white-space: nowrap; }
.del-btn { border: none; background: none; cursor: pointer; color: #9ca3af; font-size: 14px; padding: 0 2px; }
.del-btn:hover { color: #ef4444; }
.dob-row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.section-title { font-size: 11px; font-weight: 600; color: #374151; white-space: nowrap; }
.field-label { font-size: 10px; color: #6b7280; white-space: nowrap; }
.attrs-section, .lits-section { display: flex; flex-direction: column; gap: 4px; }
.section-row { display: flex; align-items: center; gap: 6px; }
.add-btn { font-size: 11px; padding: 1px 6px; border: 1px solid #cbd5e1; border-radius: 4px; background: #fff; cursor: pointer; }
.add-btn:hover { background: #f1f5f9; }
.lit-row { display: flex; gap: 4px; align-items: center; }
.lit-in { flex: 1; font-size: 11px; border: 1px solid #e2e8f0; border-radius: 3px; padding: 1px 4px; }
</style>
