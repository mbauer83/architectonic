<script setup lang="ts">
/**
 * *Connect to…* (sketch 03·11): the other end picked by name from what the diagram draws, a field that
 * narrows the list as one types, each row the element's name with its type at the right. The field is
 * focused on opening; Down walks into the list, Up from its first row goes back to the field.
 */
import { computed, nextTick, onMounted, ref } from 'vue'
import ArchimateTypeGlyph from './ArchimateTypeGlyph.vue'
import { toGlyphKey } from '../lib/glyphKey'
import { menuStep } from './canvasMenu'
import { typeWords } from './canvasTypeList'

const props = defineProps<{
  /** The element the relation starts from. */
  from: string
  members: readonly { readonly alias: string; readonly name: string; readonly type: string }[]
}>()
const emit = defineEmits<{ pick: [alias: string] }>()

const query = ref('')
const field = ref<HTMLInputElement | null>(null)
const list = ref<HTMLElement | null>(null)
const shown = computed(() => {
  const wanted = query.value.trim().toLowerCase()
  return props.members.filter((one) => !wanted || one.name.toLowerCase().includes(wanted))
})
onMounted(() => void nextTick(() => field.value?.focus()))

const walk = (event: KeyboardEvent) => {
  const rows = [...list.value?.querySelectorAll<HTMLElement>('[role="option"]') ?? []]
  const at = rows.indexOf(document.activeElement as HTMLElement)
  if (at < 0 && event.key !== 'ArrowDown') {
    if (event.key === 'Enter' && rows.length) {
      event.preventDefault()
      rows[0]?.click()
    }
    return
  }
  if (event.key === 'ArrowUp' && at === 0) {
    event.preventDefault()
    field.value?.focus()
    return
  }
  const next = menuStep(event.key, at, rows.length)
  if (next !== null) {
    event.preventDefault()
    rows[next]?.focus()
  } else if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    rows[at]?.click()
  }
}
</script>

<template>
  <div
    class="connect"
    @keydown="walk"
  >
    <p class="connect__heading">
      Connect {{ from }} to…
    </p>
    <input
      ref="field"
      v-model="query"
      class="cp-input"
      autocomplete="off"
      aria-label="The element to connect to"
      placeholder="Name of the other element…"
    >
    <div
      ref="list"
      class="connect__list"
      role="listbox"
      aria-label="Elements on this diagram"
    >
      <div
        v-for="one in shown"
        :key="one.alias"
        class="connect__row"
        role="option"
        tabindex="-1"
        :aria-selected="false"
        @click="emit('pick', one.alias)"
      >
        <span class="connect__name">{{ one.name }}</span>
        <small
          v-if="one.type"
          class="connect__type"
        >
          <ArchimateTypeGlyph
            :type="toGlyphKey(one.type)"
            :size="12"
          />{{ typeWords(one.type) }}
        </small>
      </div>
      <p
        v-if="!shown.length"
        class="connect__none"
      >
        Nothing on this diagram is called that.
      </p>
    </div>
  </div>
</template>

<style scoped>
.connect { padding: 0 4px 2px; }
.connect__heading {
  margin: 2px 2px 6px; font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: var(--faint);
  overflow-wrap: anywhere;
}
.connect__list { max-height: 260px; overflow-y: auto; overscroll-behavior: contain; margin-top: 4px; }
.connect__row {
  display: flex; gap: 8px; align-items: center; padding: 6px 4px; border-radius: 5px; cursor: pointer;
  font-size: 12.5px; color: var(--text);
}
.connect__row:hover, .connect__row:focus { background: var(--soft); outline: none; }
.connect__name { flex: 1; min-width: 0; }
.connect__type { display: inline-flex; gap: 4px; align-items: center; color: var(--faint); font-size: 11px; }
.connect__none { margin: 4px 6px; color: var(--faint); font-size: 11px; }
</style>
