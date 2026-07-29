<script setup lang="ts">
import { computed } from 'vue'
import type { DiagramOwnEntityTypeUiConfig, EntityDisplayInfo } from '../../domain'
import EntityPickerInput from './EntityPickerInput.vue'

type DiagramOnlyEntity = Record<string, unknown> & {
  id: string
  label: string
  entity_id?: string
}

const HIDDEN_PROPS = new Set(['scope', 'drilldown_diagram_id'])

const props = defineProps<{
  config: DiagramOwnEntityTypeUiConfig
  diagramEntities: Record<string, unknown>
  excludedItemId?: string
}>()
const emit = defineEmits<{ diagramEntitiesChange: [patch: Record<string, unknown>] }>()

const collectionKey = computed(() => props.config.entity_type)

const allItems = computed<DiagramOnlyEntity[]>(() => {
  const raw = props.diagramEntities[collectionKey.value]
  return Array.isArray(raw)
    ? raw.filter((item): item is DiagramOnlyEntity => Boolean(item && typeof item === 'object' && 'id' in item))
    : []
})

const items = computed<DiagramOnlyEntity[]>(() =>
  props.excludedItemId
    ? allItems.value.filter((item) => item.id !== props.excludedItemId)
    : allItems.value,
)

const canAdd = computed(() => props.config.max === null || items.value.length < props.config.max)
const canRemove = computed(() => items.value.length > props.config.min)
const permittedTypes = computed(() => props.config.permitted_mappings.entity_types)
const propertySpecs = computed(() =>
  (props.config.properties ?? []).filter((p) => !HIDDEN_PROPS.has(p.name)),
)

const updateItems = (next: DiagramOnlyEntity[]) => {
  if (props.excludedItemId) {
    const preserved = allItems.value.find((item) => item.id === props.excludedItemId)
    const full = preserved ? [preserved, ...next] : next
    emit('diagramEntitiesChange', { [collectionKey.value]: full })
  } else {
    emit('diagramEntitiesChange', { [collectionKey.value]: next })
  }
}

const addItem = () => {
  if (!canAdd.value) return
  const id = `${props.config.entity_type}-${Date.now().toString(36)}`
  updateItems([...items.value, { id, label: props.config.label }])
}
const removeItem = (id: string) => {
  if (!canRemove.value) return
  updateItems(items.value.filter((item) => item.id !== id))
}
const patchItem = (id: string, patch: Partial<DiagramOnlyEntity>) =>
  updateItems(items.value.map((item) => item.id === id ? { ...item, ...patch } : item))
const setMapping = (id: string, entity: EntityDisplayInfo) =>
  patchItem(id, { entity_id: entity.artifact_id, label: entity.name })
const propertyType = (schema: unknown): string => {
  if (!schema || typeof schema !== 'object' || !('type' in schema)) return ''
  const value = (schema as { type?: unknown }).type
  return typeof value === 'string' ? value : ''
}
const propEnumValues = (schema: unknown): string[] => {
  if (!schema || typeof schema !== 'object' || !('enum' in schema)) return []
  const value = (schema as { enum?: unknown }).enum
  return Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : []
}
</script>

<template>
  <section class="type-section">
    <div class="type-section__header">
      <span>{{ config.plural }}</span>
      <button
        class="mini-btn"
        :disabled="!canAdd"
        type="button"
        @click="addItem"
      >
        +
      </button>
    </div>
    <div
      v-for="item in items"
      :key="item.id"
      class="type-card"
    >
      <div class="card-top">
        <EntityPickerInput
          v-if="permittedTypes.length"
          class="card-picker"
          :fixed-entity-types="[...permittedTypes]"
          widenable-to="none"
          :placeholder="item.entity_id ? 'Change model mapping…' : 'Map to model entity…'"
          @select="setMapping(item.id, $event)"
        />
        <button
          class="mini-btn rm-btn"
          :disabled="!canRemove"
          type="button"
          title="Remove"
          @click="removeItem(item.id)"
        >
          ×
        </button>
      </div>
      <input
        class="inp card-label"
        :value="item.label"
        :placeholder="config.label + ' label'"
        @input="patchItem(item.id, { label: ($event.target as HTMLInputElement).value })"
      >
      <div
        v-if="propertySpecs.length"
        class="card-props"
      >
        <label
          v-for="prop in propertySpecs"
          :key="prop.name"
          class="prop-field"
        >
          <span
            v-if="propertyType(prop.schema) !== 'boolean'"
            class="prop-label"
          >{{ prop.name }}</span>
          <select
            v-if="propertyType(prop.schema) === 'string' && propEnumValues(prop.schema).length"
            class="inp"
            :value="String(item[prop.name] ?? '')"
            @change="patchItem(item.id, { [prop.name]: ($event.target as HTMLSelectElement).value })"
          >
            <option
              v-for="opt in propEnumValues(prop.schema)"
              :key="opt"
              :value="opt"
            >{{ opt || '(auto — infer from technology)' }}</option>
          </select>
          <input
            v-else-if="propertyType(prop.schema) !== 'boolean'"
            class="inp"
            :value="String(item[prop.name] ?? '')"
            :placeholder="prop.name"
            @input="patchItem(item.id, { [prop.name]: ($event.target as HTMLInputElement).value })"
          >
          <label
            v-else
            class="toggle-row"
          >
            <input
              type="checkbox"
              :checked="Boolean(item[prop.name])"
              @change="patchItem(item.id, { [prop.name]: ($event.target as HTMLInputElement).checked })"
            >
            <span class="toggle-label">{{ prop.name }}</span>
          </label>
        </label>
      </div>
    </div>
  </section>
</template>

<style scoped>
.type-section { display: grid; gap: 8px; }
.type-section__header { display: flex; align-items: center; justify-content: space-between; font-weight: 650; font-size: 12px; }
.type-card { display: flex; flex-direction: column; gap: 6px; padding: 10px; border: 1px solid #dbe3ef; border-radius: 8px; background: #fff; }
.card-top { display: flex; align-items: center; gap: 6px; }
.card-picker { flex: 1; min-width: 0; }
.rm-btn { flex-shrink: 0; }
.card-label { width: 100%; box-sizing: border-box; }
.card-props { display: flex; flex-wrap: wrap; gap: 8px; }
.prop-field { display: flex; flex-direction: column; gap: 3px; flex: 1; min-width: 120px; }
.prop-label { font-size: 11px; font-weight: 600; color: #475569; }
.toggle-row { display: flex; align-items: center; gap: 6px; cursor: pointer; padding: 4px 0; }
.toggle-label { font-size: 12px; color: #374151; }
.mini-btn { min-width: 28px; height: 28px; border: 1px solid #cbd5e1; background: #fff; border-radius: 6px; cursor: pointer; font-size: 14px; color: #374151; }
.mini-btn:disabled { opacity: .45; cursor: not-allowed; }
.inp {
  width: 100%;
  padding: 5px 8px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  font-size: 13px;
  background: white;
  color: #1e293b;
  outline: none;
  box-sizing: border-box;
}
.inp:focus { border-color: #3b82f6; box-shadow: 0 0 0 2px #bfdbfe; }
</style>
