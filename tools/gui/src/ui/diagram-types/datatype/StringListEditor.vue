<script setup lang="ts">
import { removeAt } from './ClassifierCard.helpers'

const props = defineProps<{
  items?: string[]
  label: string
  placeholder?: string
  addLabel?: string
}>()
const emit = defineEmits<{ update: [items: string[] | undefined] }>()

const list = () => props.items ?? []

function commit(next: string[]) {
  emit('update', next.length ? next : undefined)
}

function add() {
  commit([...list(), ''])
}

function update(index: number, value: string) {
  commit(list().map((item, i) => i === index ? value : item))
}

function remove(index: number) {
  commit(removeAt(list(), index))
}
</script>

<template>
  <div class="sle">
    <div class="sle-hdr">
      <span class="sle-label">{{ label }}</span>
      <button
        class="sle-add"
        type="button"
        @click="add"
      >
        {{ addLabel ?? '+ Add' }}
      </button>
    </div>
    <div
      v-for="(item, i) in list()"
      :key="i"
      class="sle-row"
    >
      <input
        class="sle-in"
        type="text"
        :value="item"
        :placeholder="placeholder ?? ''"
        @input="update(i, ($event.target as HTMLInputElement).value)"
      >
      <button
        class="sle-del"
        type="button"
        title="Remove"
        @click="remove(i)"
      >
        ×
      </button>
    </div>
  </div>
</template>

<style scoped>
.sle { display: flex; flex-direction: column; gap: 3px; }
.sle-hdr { display: flex; align-items: center; justify-content: space-between; }
.sle-label { font-size: 10px; color: #6b7280; }
.sle-add { font-size: 10px; padding: 0 6px; border: 1px solid #cbd5e1; border-radius: 4px; background: #fff; cursor: pointer; }
.sle-add:hover { background: #f1f5f9; }
.sle-row { display: flex; gap: 4px; align-items: center; }
.sle-in { flex: 1; font-size: 11px; border: 1px solid #e2e8f0; border-radius: 3px; padding: 1px 4px; }
.sle-del { border: none; background: none; cursor: pointer; color: #9ca3af; font-size: 13px; padding: 0 2px; }
.sle-del:hover { color: #ef4444; }
</style>
