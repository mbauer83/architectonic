<script setup lang="ts">
import { computed } from 'vue'
import type { Attribute } from './useDatatypeModel'
import { appendMember, attrLabel, moveInList, removeAt } from './ClassifierCard.helpers'

const props = defineProps<{
  memberIds: string[]
  attributes: Attribute[]
}>()
const emit = defineEmits<{ update: [ids: string[]] }>()

const available = computed(() =>
  props.attributes.filter((a) => !props.memberIds.includes(a.id)),
)

const nameOf = (id: string) => attrLabel(id, props.attributes)

function add(event: Event) {
  const select = event.target as HTMLSelectElement
  if (select.value) emit('update', appendMember(props.memberIds, select.value))
  select.value = ''
}
</script>

<template>
  <div class="oap">
    <span
      v-for="(id, i) in memberIds"
      :key="id"
      class="chip"
    >
      <button
        class="chip-mv"
        type="button"
        title="Move left"
        :disabled="i === 0"
        @click="emit('update', moveInList(memberIds, i, -1))"
      >‹</button>
      <span class="chip-name">{{ nameOf(id) }}</span>
      <button
        class="chip-mv"
        type="button"
        title="Move right"
        :disabled="i === memberIds.length - 1"
        @click="emit('update', moveInList(memberIds, i, 1))"
      >›</button>
      <button
        class="chip-del"
        type="button"
        title="Remove from key"
        @click="emit('update', removeAt(memberIds, i))"
      >×</button>
    </span>
    <select
      v-if="available.length"
      class="oap-add"
      title="Add an attribute to this key"
      @change="add"
    >
      <option value="">
        + attribute
      </option>
      <option
        v-for="a in available"
        :key="a.id"
        :value="a.id"
      >
        {{ a.name }}
      </option>
    </select>
  </div>
</template>

<style scoped>
.oap { display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.chip { display: inline-flex; align-items: center; gap: 1px; font-size: 11px; background: var(--indigo-soft); border: 1px solid var(--indigo-border); border-radius: 10px; padding: 0 2px 0 6px; }
.chip-name { color: var(--indigo-text); }
.chip-mv { border: none; background: none; cursor: pointer; color: var(--indigo); font-size: 12px; padding: 0 1px; }
.chip-mv:disabled { color: #c7d2fe; cursor: default; }
.chip-del { border: none; background: none; cursor: pointer; color: var(--faint); font-size: 12px; padding: 0 2px; }
.chip-del:hover { color: var(--danger); }
.oap-add { font-size: 10px; border: 1px dashed var(--border-strong); border-radius: 10px; padding: 1px 4px; background: var(--surface); cursor: pointer; color: var(--muted); }
</style>
