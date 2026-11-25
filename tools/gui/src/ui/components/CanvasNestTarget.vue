<script setup lang="ts">
/**
 * *Nest in…* (sketch 03·9–11): what on this diagram may take the element. One of the diagram's own boxes
 * takes anything, as diagram content only; an element takes it only by a relationship of the containment
 * kind the ontology permits from the element's type to it (`relationship_kind_map`), and choosing one
 * asks *Make X part of Y?* — each choice a whole sentence, *Don't nest* last — because nesting in an
 * element is that relation, a model change kept with the session. An element no containment is
 * permitted into is not listed. The field is focused on opening; Down walks into the list.
 */
import { computed, inject, nextTick, onMounted, ref, watch } from 'vue'
import { modelServiceKey } from '../keys'
import { containmentKinds } from './canvasParts'
import ArchimateTypeGlyph from './ArchimateTypeGlyph.vue'
import { toGlyphKey } from '../lib/glyphKey'
import { menuStep } from './canvasMenu'
import { typeWords } from './canvasTypeList'

interface Shape { readonly alias: string; readonly name: string; readonly type?: string }

const props = defineProps<{
  element: Shape
  /** The diagram's own boxes, but the one the element is in. */
  boxes: readonly Shape[]
  /** The other elements on the diagram. */
  members: readonly Shape[]
  /** The element a drop asked to nest it in: the question opens on it, or says it may not take it. */
  ask?: string | null
}>()
const emit = defineEmits<{ box: [alias: string]; relate: [container: string, kind: string]; cancel: [] }>()
const svc = inject(modelServiceKey)!

const query = ref('')
const field = ref<HTMLInputElement | null>(null)
const root = ref<HTMLElement | null>(null)
/** The containment relationships permitted from each container type to the element's, as asked. */
const containments = ref<ReadonlyMap<string, readonly string[]>>(new Map())
const asking = ref<Shape | null>(null)

onMounted(async () => {
  await nextTick()
  field.value?.focus()
  const type = props.element.type
  if (!type) return
  const types = [...new Set(props.members.flatMap((one) => (one.type ? [one.type] : [])))]
  const answers = await Promise.all(types.map(async (container): Promise<readonly [string, readonly string[]]> => {
    try {
      return [container, await containmentKinds(svc, container, type)]
    } catch {
      return [container, []]
    }
  }))
  containments.value = new Map(answers)
  const dropped = props.members.find((one) => one.alias === props.ask)
  if (dropped) {
    if (containers.value.includes(dropped)) asking.value = dropped
    else refused.value = `${dropped.name} may not contain ${props.element.name}: the ontology permits no part-of `
      + `relationship from a ${typeWords(dropped.type ?? '')} to a ${typeWords(type)}.`
  }
})
const refused = ref('')

const matches = (one: Shape) => !query.value.trim() || one.name.toLowerCase().includes(query.value.trim().toLowerCase())
const boxes = computed(() => props.boxes.filter(matches))
const containers = computed(() =>
  props.members.filter((one) => one.type && (containments.value.get(one.type)?.length ?? 0) > 0 && matches(one)))

// The question opens on its first answer, as a menu does.
watch(asking, () => void nextTick(() => root.value?.querySelector<HTMLElement>('[role="menuitem"]')?.focus()))

const choose = (one: Shape, kind: 'box' | 'element') => {
  if (kind === 'box') emit('box', one.alias)
  else asking.value = one
}

const walk = (event: KeyboardEvent) => {
  const rows = [...root.value?.querySelectorAll<HTMLElement>('[role="option"], [role="menuitem"]') ?? []]
  const at = rows.indexOf(document.activeElement as HTMLElement)
  if (at < 0 && event.key !== 'ArrowDown') return
  if (event.key === 'ArrowUp' && at === 0 && !asking.value) {
    event.preventDefault()
    field.value?.focus()
    return
  }
  const next = menuStep(event.key, at, rows.length)
  if (next !== null) {
    event.preventDefault()
    rows[next]?.focus()
  } else if ((event.key === 'Enter' || event.key === ' ') && at >= 0) {
    event.preventDefault()
    rows[at]?.click()
  }
}
const sentence = (kind: string, container: Shape) =>
  `${props.element.name} becomes part of ${container.name} — ${typeWords(kind.replace(/^archimate-/, ''))}`
</script>

<template>
  <div
    ref="root"
    class="nest"
    @keydown="walk"
  >
    <p
      v-if="refused"
      class="cp-alert"
      role="alert"
    >
      {{ refused }}
    </p>
    <!-- A drop on an element that may not hold it says why, and offers no list of somewhere else (03·10). -->
    <template v-if="!asking && !refused">
      <p class="nest__heading">
        Nest {{ element.name }} in…
      </p>
      <input
        ref="field"
        v-model="query"
        class="cp-input"
        autocomplete="off"
        aria-label="The box or element to nest it in"
        placeholder="Name of a box or an element…"
      >
      <div
        class="nest__list"
        role="listbox"
        aria-label="What may take it"
      >
        <div
          v-for="one in boxes"
          :key="one.alias"
          class="nest__row"
          role="option"
          tabindex="-1"
          :aria-selected="false"
          @click="choose(one, 'box')"
        >
          <span class="nest__name">{{ one.name }}</span>
          <small>a box · on this diagram only</small>
        </div>
        <div
          v-for="one in containers"
          :key="one.alias"
          class="nest__row"
          role="option"
          tabindex="-1"
          :aria-selected="false"
          @click="choose(one, 'element')"
        >
          <span class="nest__name">{{ one.name }}</span>
          <small><ArchimateTypeGlyph
            v-if="one.type"
            :type="toGlyphKey(one.type)"
            :size="12"
          />{{ typeWords(one.type ?? '') }} · a model change</small>
        </div>
        <p
          v-if="!boxes.length && !containers.length"
          class="nest__none"
        >
          Nothing on this diagram may take it.
        </p>
      </div>
    </template>
    <div
      v-else-if="asking"
      class="cp-form"
      role="menu"
      :aria-label="`Make ${element.name} part of ${asking.name}?`"
    >
      <h3 class="cp-title">
        Make {{ element.name }} part of {{ asking.name }}?
      </h3>
      <button
        v-for="kind in containments.get(asking.type ?? '') ?? []"
        :key="kind"
        type="button"
        class="cp-btn nest__choice"
        role="menuitem"
        @click="emit('relate', asking.alias, kind)"
      >
        {{ sentence(kind, asking) }}
      </button>
      <p class="cp-note">
        ArchiMate reads nesting in an element as this relationship, so nesting without it is not offered.
        It is a model change, written when you Save.
      </p>
      <button
        type="button"
        class="cp-btn"
        role="menuitem"
        @click="emit('cancel')"
      >
        Don't nest
      </button>
    </div>
  </div>
</template>

<style scoped>
.nest { padding: 0 4px 2px; }
.nest__heading {
  margin: 2px 2px 6px; font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: var(--faint);
}
.nest__list { max-height: 260px; overflow-y: auto; overscroll-behavior: contain; margin-top: 4px; }
.nest__row {
  display: flex; gap: 8px; align-items: center; padding: 6px 4px; border-radius: 5px; cursor: pointer;
  font-size: 12.5px; color: var(--text);
}
.nest__row:hover, .nest__row:focus { background: var(--soft); outline: none; }
.nest__row small { display: inline-flex; gap: 4px; align-items: center; color: var(--faint); font-size: 11px; }
.nest__name { flex: 1; min-width: 0; }
.nest__none { margin: 4px 6px; color: var(--faint); font-size: 11px; }
.nest__choice { text-align: left; white-space: normal; }
</style>
