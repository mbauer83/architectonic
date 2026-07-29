<script setup lang="ts">
import type { Attribute, UniqueKey } from './useDatatypeModel'
import { removeAt } from './ClassifierCard.helpers'
import OrderedAttrPicker from './OrderedAttrPicker.vue'

const props = defineProps<{
  attributes: Attribute[]
  identity?: string[]
  uniqueKeys?: UniqueKey[]
}>()
const emit = defineEmits<{
  updateIdentity: [ids: string[] | undefined]
  updateUniqueKeys: [keys: UniqueKey[] | undefined]
}>()

const identityIds = () => props.identity ?? []
const keys = () => props.uniqueKeys ?? []

function setIdentity(ids: string[]) {
  emit('updateIdentity', ids.length ? ids : undefined)
}

function commitKeys(next: UniqueKey[]) {
  emit('updateUniqueKeys', next.length ? next : undefined)
}

function addKey() {
  commitKeys([...keys(), { attribute_ids: [] }])
}

function patchKey(index: number, patch: Partial<UniqueKey>) {
  commitKeys(keys().map((k, i) => i === index ? { ...k, ...patch } : k))
}

function removeKey(index: number) {
  commitKeys(removeAt(keys(), index))
}
</script>

<template>
  <section class="keys">
    <div class="keys-row">
      <span class="keys-label">Identity</span>
      <OrderedAttrPicker
        :member-ids="identityIds()"
        :attributes="attributes"
        @update="setIdentity"
      />
    </div>

    <div class="keys-hdr">
      <span class="keys-label">Unique keys</span>
      <button
        class="keys-add"
        type="button"
        :disabled="!attributes.length"
        @click="addKey"
      >
        + Unique key
      </button>
    </div>
    <div
      v-for="(key, i) in keys()"
      :key="i"
      class="key-row"
    >
      <input
        class="key-name"
        type="text"
        :value="key.name ?? ''"
        placeholder="name (optional)"
        @input="patchKey(i, { name: ($event.target as HTMLInputElement).value || undefined })"
      >
      <OrderedAttrPicker
        :member-ids="key.attribute_ids"
        :attributes="attributes"
        @update="(ids) => patchKey(i, { attribute_ids: ids })"
      />
      <button
        class="key-del"
        type="button"
        title="Remove unique key"
        @click="removeKey(i)"
      >
        ×
      </button>
    </div>
  </section>
</template>

<style scoped>
.keys { display: flex; flex-direction: column; gap: 5px; }
.keys-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.keys-hdr { display: flex; align-items: center; justify-content: space-between; }
.keys-label { font-size: 11px; font-weight: 600; color: #374151; white-space: nowrap; }
.keys-add { font-size: 11px; padding: 1px 6px; border: 1px solid #cbd5e1; border-radius: 4px; background: #fff; cursor: pointer; }
.keys-add:disabled { opacity: 0.5; cursor: not-allowed; }
.key-row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.key-name { width: 110px; font-size: 11px; border: 1px solid #e2e8f0; border-radius: 3px; padding: 1px 4px; }
.key-del { border: none; background: none; cursor: pointer; color: #9ca3af; font-size: 14px; padding: 0 2px; }
.key-del:hover { color: #ef4444; }
</style>
