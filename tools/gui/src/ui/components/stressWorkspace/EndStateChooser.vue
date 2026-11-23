<script setup lang="ts">
/**
 * The End state cell: one press opens a field and the end states, which narrow as you type; an
 * unknown name offers *Create end state "…"* on Enter. The same chooser opens on `M` from a focused
 * stressor in either tab. Choosing emits the end state's row id, or the new name to create.
 */
import { computed, nextTick, ref } from 'vue'
import type { DocumentTableRow } from '../../../domain/schemas/candidates'
import { endStateName } from '../../../domain/stressAnalysis/analysisRows'

const props = defineProps<{ endStates: readonly DocumentTableRow[]; current: string }>()
const emit = defineEmits<{ choose: [rowId: string]; create: [name: string] }>()

const open = ref(false)
const query = ref('')
const active = ref(0)
const field = ref<HTMLInputElement | null>(null)

const nameOf = (row: DocumentTableRow): string => endStateName(props.endStates, row.row_id)
const currentName = computed(() => (props.current ? endStateName(props.endStates, props.current) : ''))
const matches = computed(() => {
  const wanted = query.value.trim().toLowerCase()
  return props.endStates.filter((row) => !wanted || nameOf(row).toLowerCase().includes(wanted))
})
const creatable = computed(() => {
  const name = query.value.trim()
  return name !== '' && !props.endStates.some((row) => nameOf(row).toLowerCase() === name.toLowerCase())
})

const show = async () => {
  open.value = true
  query.value = ''
  active.value = 0
  await nextTick()
  field.value?.focus()
}
const close = () => { open.value = false }
const choose = (row: DocumentTableRow) => { emit('choose', row.row_id); close() }
const create = () => { emit('create', query.value.trim()); close() }

const onKey = (event: KeyboardEvent) => {
  const count = matches.value.length + (creatable.value ? 1 : 0)
  if (event.key === 'ArrowDown') active.value = Math.min(active.value + 1, count - 1)
  else if (event.key === 'ArrowUp') active.value = Math.max(active.value - 1, 0)
  else if (event.key === 'Enter') {
    const row = matches.value[active.value]
    if (row) choose(row)
    else if (creatable.value) create()
  } else if (event.key === 'Escape') close()
  else return
  event.preventDefault()
  event.stopPropagation()
}

defineExpose({ show })
</script>

<template>
  <span class="es-chooser">
    <button
      type="button"
      class="es-pick"
      :aria-expanded="open"
      aria-haspopup="listbox"
      data-testid="end-state-pick"
      @click.stop="open ? close() : show()"
    >
      <span v-if="currentName">{{ currentName }}</span>
      <span
        v-else
        class="none"
      >choose…</span>
    </button>
    <div
      v-if="open"
      class="es-menu"
      role="dialog"
      aria-label="Choose an end state"
      @click.stop
    >
      <input
        ref="field"
        v-model="query"
        class="es-field"
        placeholder="Type to narrow, or name a new one"
        aria-label="End state"
        @input="active = 0"
        @keydown="onKey"
        @blur="close"
      >
      <ul role="listbox">
        <li
          v-for="(row, index) in matches"
          :key="row.row_id"
          role="option"
          :aria-selected="index === active"
          :class="{ active: index === active }"
          @mousedown.prevent="choose(row)"
        >
          <span class="rid">{{ row.row_id }}</span> {{ nameOf(row) }}
        </li>
        <li
          v-if="creatable"
          role="option"
          :aria-selected="active === matches.length"
          :class="{ active: active === matches.length, create: true }"
          @mousedown.prevent="create"
        >
          Create end state “{{ query.trim() }}” <kbd>Enter</kbd>
        </li>
        <li
          v-if="!matches.length && !creatable"
          class="empty"
        >
          No end states yet: type a name.
        </li>
      </ul>
    </div>
  </span>
</template>

<style scoped>
.es-chooser { position: relative; display: inline-block; }
.es-pick {
  display: inline-flex; gap: 4px; align-items: center; max-width: 170px; text-align: left;
  border: 1px solid var(--border); background: var(--surface); color: var(--text);
  border-radius: 4px; padding: 2px 6px; font-size: 12px; cursor: pointer;
}
.es-pick::after { content: '▾'; color: var(--muted); font-size: 10px; }
.es-pick:hover, .es-pick:focus-visible { border-color: var(--accent); }
.es-pick .none { color: var(--muted); }
.es-menu {
  position: absolute; z-index: 30; right: 0; top: calc(100% + 4px); width: 250px; padding: 6px;
  background: var(--surface); border: 1px solid var(--border-strong, var(--border)); border-radius: 6px;
  box-shadow: 0 6px 18px #0002;
}
.es-field { width: 100%; font: inherit; font-size: 12px; padding: 3px 6px; }
.es-menu ul { list-style: none; margin: 4px 0 0; padding: 0; max-height: 200px; overflow: auto; font-size: 12px; }
.es-menu li { padding: 3px 6px; border-radius: 4px; cursor: pointer; }
.es-menu li.active { background: var(--accent-soft, #eff6ff); color: var(--accent-strong, #1d4ed8); }
.es-menu li.empty { color: var(--muted); cursor: default; }
.es-menu .rid { color: var(--muted); font-family: ui-monospace, monospace; font-size: 11px; }
.es-menu kbd { font: 10px ui-monospace, monospace; border: 1px solid var(--border); border-radius: 3px; padding: 0 3px; }
</style>
