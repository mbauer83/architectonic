<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Attribute } from './useDatatypeModel'
import type { TypeOption, TypeOptionGroup } from './ClassifierCard.helpers'
import { optionKey, refFromOptionKey } from './ClassifierCard.helpers'

const props = defineProps<{
  attr: Attribute
  typeOptions: TypeOption[]
}>()
const emit = defineEmits<{
  update: [patch: Partial<Attribute>]
  remove: []
  newClassifier: []
}>()

const expanded = ref(false)
const hasMeta = computed(() => Boolean(props.attr.optional || props.attr.role || props.attr.provenance))

const optionGroups: TypeOptionGroup[] = ['Primitives', 'This diagram', 'Engagement', 'Enterprise']
const optionsFor = (group: TypeOptionGroup) => props.typeOptions.filter((o) => o.group === group)

function onTypeChange(event: Event) {
  const select = event.target as HTMLSelectElement
  const key = select.value
  if (key === '__new_classifier__') {
    select.value = optionKey(props.attr.type)
    emit('newClassifier')
    return
  }
  emit('update', { type: refFromOptionKey(key, props.typeOptions) })
}
</script>

<template>
  <div class="attr">
    <div class="attr-row">
      <button
        class="chev"
        type="button"
        :class="{ open: expanded, dot: hasMeta }"
        :title="expanded ? 'Hide details' : 'Show details (optional, role, provenance)'"
        @click="expanded = !expanded"
      >
        ▸
      </button>
      <input
        type="text"
        class="attr-name"
        :value="attr.name"
        placeholder="name"
        @input="emit('update', { name: ($event.target as HTMLInputElement).value })"
      >
      <select
        class="attr-type"
        :value="optionKey(attr.type)"
        title="Attribute type"
        @change="onTypeChange"
      >
        <option
          value=""
          disabled
        >
          Select type…
        </option>
        <optgroup
          v-for="group in optionGroups"
          :key="group"
          :label="group"
        >
          <option
            v-for="option in optionsFor(group)"
            :key="option.key"
            :value="option.key"
          >
            {{ option.label }}
          </option>
        </optgroup>
        <option value="__new_classifier__">
          + New classifier
        </option>
      </select>
      <input
        type="text"
        class="attr-mult"
        :value="attr.multiplicity ?? ''"
        placeholder="0..1"
        title="Multiplicity (collection cardinality: 1, 0..1, 1..*, *)"
        @input="emit('update', { multiplicity: ($event.target as HTMLInputElement).value || undefined })"
      >
      <button
        class="del-btn"
        type="button"
        title="Remove attribute"
        @click="emit('remove')"
      >
        ×
      </button>
    </div>
    <div
      v-if="expanded"
      class="attr-meta"
    >
      <label class="meta-chk">
        <input
          type="checkbox"
          :checked="!!attr.optional"
          @change="emit('update', { optional: ($event.target as HTMLInputElement).checked || undefined })"
        > optional
      </label>
      <input
        type="text"
        class="meta-in"
        :value="attr.role ?? ''"
        placeholder="role"
        title="This attribute's role"
        @input="emit('update', { role: ($event.target as HTMLInputElement).value || undefined })"
      >
      <input
        type="text"
        class="meta-in"
        :value="attr.provenance ?? ''"
        placeholder="provenance"
        title="Where this attribute comes from"
        @input="emit('update', { provenance: ($event.target as HTMLInputElement).value || undefined })"
      >
    </div>
  </div>
</template>

<style scoped>
.attr { display: flex; flex-direction: column; gap: 2px; }
.attr-row { display: flex; gap: 4px; align-items: center; }
.chev { border: none; background: none; cursor: pointer; color: #9ca3af; font-size: 11px; padding: 0; transition: transform .1s; position: relative; }
.chev.open { transform: rotate(90deg); }
.chev.dot::after { content: ''; position: absolute; top: 0; right: -2px; width: 4px; height: 4px; border-radius: 50%; background: #6366f1; }
.attr-name { width: 90px; font-size: 11px; border: 1px solid #e2e8f0; border-radius: 3px; padding: 1px 4px; }
.attr-type { width: 130px; font-size: 11px; border: 1px solid #e2e8f0; border-radius: 3px; padding: 1px 4px; background: #fff; }
.attr-mult { width: 55px; font-size: 11px; border: 1px solid #e2e8f0; border-radius: 3px; padding: 1px 4px; }
.del-btn { border: none; background: none; cursor: pointer; color: #9ca3af; font-size: 14px; padding: 0 2px; }
.del-btn:hover { color: #ef4444; }
.attr-meta { display: flex; gap: 6px; align-items: center; padding-left: 18px; flex-wrap: wrap; }
.meta-chk { font-size: 11px; color: #6b7280; display: flex; align-items: center; gap: 2px; cursor: pointer; }
.meta-in { width: 120px; font-size: 11px; border: 1px solid #e2e8f0; border-radius: 3px; padding: 1px 4px; }
</style>
