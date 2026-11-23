<script setup lang="ts">
import { computed, inject, onMounted, ref, watch } from 'vue'
import { Effect } from 'effect'
import { modelServiceKey } from '../keys'
import type { DiagramContext } from '../../domain'
import ArchimateTypeGlyph from './ArchimateTypeGlyph.vue'
import { toGlyphKey } from '../lib/glyphKey'
import type { CanvasCommand } from '../../ports/diagramWriteBodies'

const props = defineProps<{ context: DiagramContext }>()
const emit = defineEmits<{ apply: [command: CanvasCommand]; cancel: [] }>()
const svc = inject(modelServiceKey)!
const search = ref('')
const type = ref('')
const name = ref('')
const summary = ref('')
const group = ref('')
const specialization = ref('')
const specs = ref<readonly { slug: string; name: string }[]>([])
const fields = ref<readonly string[]>([])
const attributes = ref<Record<string, string>>({})
const error = ref('')
const recentKey = 'diagram-recent-model-types'
const recent = ref<string[]>([])
const types = ref<{ type: string; domain: string }[]>([])
const projects = ref<{ slug: string; name: string }[]>([])
const counts = new Map<string, number>()
for (const entity of props.context.entities)
  counts.set(entity.group ?? '', (counts.get(entity.group ?? '') ?? 0) + 1)
const sections = computed(() => {
  const groups = new Map<string, string[]>()
  const used = new Set(props.context.entities.map((e) => e.artifact_type))
  const eligible = types.value.filter((t) => t.type.toLowerCase().includes(search.value.toLowerCase()))
  const ordered = [
    ...recent.value.flatMap((r) => eligible.filter((t) => t.type === r)),
    ...eligible.filter((t) => !recent.value.includes(t.type)),
  ]
  for (const item of ordered) {
    const label = recent.value.includes(item.type)
      ? 'Recently used'
      : used.has(item.type)
        ? 'In this diagram'
        : item.domain
    groups.set(label, [...(groups.get(label) ?? []), item.type])
  }
  return [...groups].sort(([a], [b]) => priority(a) - priority(b))
})
const priority = (s: string) => (s === 'Recently used' ? 0 : s === 'In this diagram' ? 1 : 2)
onMounted(async () => {
  try {
    const stored: unknown = JSON.parse(localStorage.getItem(recentKey) ?? '[]')
    if (Array.isArray(stored)) recent.value = stored.filter((v): v is string => typeof v === 'string')
    const [palette, groups] = await Promise.all([
      Effect.runPromise(svc.listDiagramElementTypes(props.context.diagram.diagram_type)),
      Effect.runPromise(svc.listGroups('model-projects')),
    ])
    types.value = palette.map((row) => ({ type: String(row.artifact_type), domain: String(row.domain) }))
    projects.value = [...(groups['model-projects'] ?? [])]
      .filter((p) => !p.archived)
      .sort(
        (a, b) => (counts.get(b.slug) ?? 0) - (counts.get(a.slug) ?? 0) || a.name.localeCompare(b.name),
      )
    group.value = projects.value[0]?.slug ?? 'uncategorized'
  } catch (e) {
    error.value = String(e)
  }
})
watch(type, async (selected) => {
  try {
    const g = await Effect.runPromise(svc.getAuthoringGuidance({ entityTypes: [selected] }))
    if (type.value === selected) specs.value = g.entity_types?.[0]?.specializations ?? []
  } catch (e) {
    error.value = String(e)
  }
})
watch([type, specialization], async ([selected, spec]) => {
  try {
    const schema = await Effect.runPromise(svc.getEntitySchemata(selected, spec || undefined))
    if (selected === type.value && spec === specialization.value) fields.value = schema.properties
  } catch (e) {
    error.value = String(e)
  }
})
const submit = async () => {
  try {
    const id = await Effect.runPromise(
      svc.allocateDiagramEntityId({
        diagram_type: props.context.diagram.diagram_type,
        entity_type: type.value,
        scope: 'model',
        name_hint: name.value,
      }),
    )
    localStorage.setItem(
      recentKey,
      JSON.stringify([type.value, ...recent.value.filter((t) => t !== type.value)].slice(0, 12)),
    )
    emit('apply', {
      op: 'model.element.create',
      artifact_type: type.value,
      artifact_id: id.id,
      name: name.value.trim(),
      summary: summary.value,
      group: group.value,
      specializations: specialization.value ? [specialization.value] : [],
      attributes: attributes.value,
    })
  } catch (e) {
    error.value = String(e)
  }
}
const walk = (event: KeyboardEvent) => {
  const box = event.currentTarget as HTMLElement
  const buttons = [...box.querySelectorAll('button')]
  const at = buttons.indexOf(document.activeElement as HTMLButtonElement)
  if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
    event.preventDefault()
    const next =
      event.key === 'End'
        ? buttons.length - 1
        : event.key === 'Home'
          ? 0
          : at + (event.key === 'ArrowDown' ? 1 : -1)
    buttons[Math.max(0, Math.min(buttons.length - 1, next))]?.focus()
  } else if (event.key.length === 1 && event.target instanceof HTMLButtonElement) {
    box.querySelector('input')?.focus()
  }
}
</script>
<template>
  <div
    v-if="!type"
    @keydown="walk"
  >
    <label>Add element <input
      v-model="search"
      type="search"
      placeholder="Filter types"
      autofocus
    ></label>
    <div class="type-list">
      <section
        v-for="[section, entries] in sections"
        :key="section"
      >
        <h4>{{ priority(section) === 2 ? 'ArchiMate · ' : '' }}{{ section }}</h4>
        <button
          v-for="t in entries"
          :key="t"
          type="button"
          @click="type = t"
        >
          <ArchimateTypeGlyph
            :type="toGlyphKey(t)"
            :size="16"
          /> {{ t }}
        </button>
      </section>
    </div>
  </div>
  <form
    v-else
    @submit.prevent="submit"
  >
    <h4>Create {{ type }}</h4>
    <label>Name <input
      v-model="name"
      required
      autofocus
    ></label>
    <label>Project
      <select v-model="group">
        <option
          v-for="p in projects"
          :key="p.slug"
          :value="p.slug"
        >{{ p.name }}</option>
      </select></label>
    <label v-if="specs.length">Specialization
      <select v-model="specialization">
        <option value="">None</option>
        <option
          v-for="s in specs"
          :key="s.slug"
          :value="s.slug"
        >{{ s.name }}</option>
      </select></label>
    <details>
      <summary>More fields</summary>
      <label>Summary <input v-model="summary"></label>
      <label
        v-for="field in fields"
        :key="field"
      >{{ field }} <input v-model="attributes[field]"></label>
    </details>
    <button
      type="submit"
      :disabled="!name.trim()"
    >
      Add to diagram
    </button>
  </form>
  <p
    v-if="error"
    role="alert"
  >
    {{ error }}
  </p>
</template>
<style scoped>
.type-list {
  max-height: 260px;
  overflow: auto;
}
button {
  display: flex;
  gap: 0.5rem;
  align-items: center;
  width: 100%;
}
label,
input,
select {
  display: block;
  width: 100%;
}
h4 {
  margin: 0.5rem 0;
}
</style>
