<script setup lang="ts">
import { inject, nextTick, onMounted, ref, watch } from 'vue'
import { Effect } from 'effect'
import { modelServiceKey } from '../keys'
import type { DiagramContext, EntityDisplayInfo } from '../../domain'
import ArchimateTypeGlyph from './ArchimateTypeGlyph.vue'
import { toGlyphKey } from '../lib/glyphKey'
import type { CanvasCommand } from '../../ports/diagramWriteBodies'
import CanvasElementPicker from './CanvasElementPicker.vue'
import { noteRecentType, typeWords } from './canvasTypeList'
import { projectsByUse } from './canvasProjects'
import { NO_COLLECTION } from './ArtifactHomeSelect.helpers'

const props = defineProps<{ context: DiagramContext }>()
const emit = defineEmits<{ apply: [command: CanvasCommand]; add: [entity: EntityDisplayInfo]; cancel: [] }>()
const svc = inject(modelServiceKey)!
const type = ref('')
const name = ref('')
const summary = ref('')
const group = ref('')
const specialization = ref('')
const specs = ref<readonly { slug: string; name: string }[]>([])
const fields = ref<readonly string[]>([])
const attributes = ref<Record<string, string>>({})
const error = ref('')
const nameField = ref<HTMLInputElement | null>(null)
const projects = ref<readonly { slug: string; name: string }[]>([])
const more = ref(false)
onMounted(async () => {
  try {
    const list = await Effect.runPromise(svc.listGroups('model-project'))
    projects.value = projectsByUse(list, props.context.entities.map((entity) => entity.group))
    group.value = projects.value[0]?.slug ?? NO_COLLECTION
  } catch (e) {
    error.value = String(e)
  }
})
/** A type chosen in the picker: the reduced form opens on it, named with what was typed there. */
const chosen = async (picked: string, typed: string) => {
  type.value = picked
  name.value = typed
  await nextTick()
  nameField.value?.focus()
}
watch(type, async (selected) => {
  if (!selected) return
  try {
    const g = await Effect.runPromise(svc.getAuthoringGuidance({ entityTypes: [selected] }))
    if (type.value === selected) specs.value = g.entity_types?.[0]?.specializations ?? []
  } catch (e) {
    error.value = String(e)
  }
})
watch([type, specialization], async ([selected, spec]) => {
  if (!selected) return
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
    noteRecentType(type.value)
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
</script>
<template>
  <CanvasElementPicker
    v-if="!type"
    :context="context"
    @add="emit('add', $event)"
    @create="chosen"
  />
  <form
    v-else
    class="cp-form"
    @submit.prevent="submit"
  >
    <h3 class="cp-title">
      New element
    </h3>
    <label class="cp-field">
      <span>Name</span>
      <input
        ref="nameField"
        v-model="name"
        class="cp-input"
        required
      >
    </label>
    <div class="cp-field">
      <span>Type</span>
      <button
        type="button"
        class="cp-btn cp-btn--sm cp-type"
        title="choose another type"
        @click="type = ''"
      >
        <ArchimateTypeGlyph
          :type="toGlyphKey(type)"
          :size="14"
        />{{ typeWords(type) }} ▾
      </button>
    </div>
    <label
      v-if="specs.length"
      class="cp-field"
    >
      <span>Specialization</span>
      <select
        v-model="specialization"
        class="cp-input"
      >
        <option value="">— none —</option>
        <option
          v-for="s in specs"
          :key="s.slug"
          :value="s.slug"
        >{{ s.name }}</option>
      </select>
    </label>
    <label class="cp-field">
      <span>Project</span>
      <select
        v-model="group"
        class="cp-input"
      >
        <option
          v-for="p in projects"
          :key="p.slug"
          :value="p.slug"
        >{{ p.name }}</option>
      </select>
    </label>
    <template v-if="more">
      <p class="cp-section">
        Declared by {{ typeWords(type) }}
      </p>
      <label class="cp-field">
        <span>Summary</span>
        <input
          v-model="summary"
          class="cp-input"
        >
      </label>
      <label
        v-for="field in fields"
        :key="field"
        class="cp-field"
      >
        <span>{{ field }}</span>
        <input
          v-model="attributes[field]"
          class="cp-input"
        >
      </label>
    </template>
    <p class="cp-note">
      Created as a draft. Written to the model when you Save, together with the diagram.
    </p>
    <div class="cp-row-end">
      <button
        type="button"
        class="cp-btn cp-btn--start"
        @click="more = !more"
      >
        {{ more ? 'Fewer fields' : 'More fields' }}
      </button>
      <button
        type="button"
        class="cp-btn"
        @click="emit('cancel')"
      >
        Cancel
      </button>
      <button
        type="submit"
        class="cp-btn cp-btn--primary"
        :disabled="!name.trim()"
      >
        Create draft <kbd>↵</kbd>
      </button>
    </div>
    <p
      v-if="error"
      class="cp-alert"
      role="alert"
    >
      {{ error }}
    </p>
  </form>
</template>
