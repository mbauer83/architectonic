<script setup lang="ts">
/** The layered-exploration/motivation-support builder panel: pick roots either by name/id
 * or by criteria, pick what kind of indirectly-connected neighbor to pull in, a
 * certainty-inclusion toggle, and a hop bound — no YAML or formula/text query input
 * anywhere. Purely a form; the parent owns execution. */
import { ref, watch } from 'vue'
import type { CriteriaCatalog, EntityDisplayInfo } from '../../domain'
import type { GroupNode } from '../../domain/viewpointCriteria'
import { mkGroup } from '../../domain/viewpointCriteria'
import { PRESET_DEFAULTS, type LayeredPreset } from '../views/LayeredExplorationView.helpers'
import EntityPickerInput from './EntityPickerInput.vue'
import CriteriaTreeBuilder from './CriteriaTreeBuilder.vue'

const props = defineProps<{ catalog: CriteriaCatalog }>()
const emit = defineEmits<{
  render: [params: {
    rootEntityIds: readonly string[]
    rootCriteria: GroupNode | null
    neighborCriteria: GroupNode
    includePotential: boolean
    maxHops: number
  }]
}>()

const preset = ref<LayeredPreset>('layered')
const rootMode = ref<'ids' | 'criteria'>('ids')
const selectedRoots = ref<EntityDisplayInfo[]>([])
const rootCriteria = ref<GroupNode>(mkGroup('entity'))
const neighborCriteria = ref<GroupNode>(PRESET_DEFAULTS.layered.neighborCriteria())
const includePotential = ref(false)
const maxHops = ref(4)

watch(preset, (value) => { neighborCriteria.value = PRESET_DEFAULTS[value].neighborCriteria() })

const addRoot = (entity: EntityDisplayInfo): void => {
  if (!selectedRoots.value.some((r) => r.artifact_id === entity.artifact_id)) selectedRoots.value = [...selectedRoots.value, entity]
}
const removeRoot = (id: string): void => { selectedRoots.value = selectedRoots.value.filter((r) => r.artifact_id !== id) }

const canRender = () => rootMode.value === 'criteria' || selectedRoots.value.length > 0

const render = (): void => {
  if (!canRender()) return
  emit('render', {
    rootEntityIds: selectedRoots.value.map((r) => r.artifact_id),
    rootCriteria: rootMode.value === 'criteria' ? rootCriteria.value : null,
    neighborCriteria: neighborCriteria.value,
    includePotential: includePotential.value,
    maxHops: maxHops.value,
  })
}
</script>

<template>
  <div class="builder-panel">
    <div class="builder-row">
      <span class="builder-label">View:</span>
      <button
        v-for="p in (['layered', 'motivation-support'] as const)"
        :key="p"
        class="preset-btn"
        :class="{ 'preset-btn--active': preset === p }"
        @click="preset = p"
      >
        {{ PRESET_DEFAULTS[p].label }}
      </button>
    </div>

    <h3>{{ PRESET_DEFAULTS[preset].neighborLabel }}</h3>
    <CriteriaTreeBuilder
      v-model="neighborCriteria"
      group-kind="entity"
      :catalog="props.catalog"
      is-root
    />

    <div class="builder-row">
      <label>
        <input
          v-model="includePotential"
          type="checkbox"
        >
        Include potential (uncertain) relationships
      </label>
    </div>
    <div class="builder-row">
      <label for="max-hops">Hop bound:</label>
      <input
        id="max-hops"
        v-model.number="maxHops"
        type="number"
        min="2"
        max="10"
      >
    </div>

    <!-- Root selection is deliberately last: EntityPickerInput's results dropdown is
    fixed-positioned and sized to fill the remaining viewport below it while open (so it
    never gets clipped by page overflow) — placing it after every other control means
    nothing the user still needs to reach (Render included) ever sits underneath it. -->
    <div class="builder-row">
      <span class="builder-label">{{ PRESET_DEFAULTS[preset].rootLabel }}:</span>
      <button
        class="mode-btn"
        :class="{ 'mode-btn--active': rootMode === 'ids' }"
        @click="rootMode = 'ids'"
      >
        By name/id
      </button>
      <button
        class="mode-btn"
        :class="{ 'mode-btn--active': rootMode === 'criteria' }"
        @click="rootMode = 'criteria'"
      >
        By criteria
      </button>
    </div>

    <div v-if="rootMode === 'ids'">
      <EntityPickerInput
        placeholder="Search entities to add as roots…"
        @select="addRoot"
      />
      <ul class="root-chips">
        <li
          v-for="root in selectedRoots"
          :key="root.artifact_id"
          class="root-chip"
        >
          {{ root.name }}
          <button
            class="chip-remove"
            :aria-label="`Remove ${root.name}`"
            @click="removeRoot(root.artifact_id)"
          >
            ×
          </button>
        </li>
      </ul>
    </div>
    <CriteriaTreeBuilder
      v-else
      v-model="rootCriteria"
      group-kind="entity"
      :catalog="props.catalog"
      is-root
    />

    <button
      class="render-btn"
      :disabled="!canRender()"
      @click="render"
    >
      Render
    </button>
  </div>
</template>

<style scoped>
.builder-panel { padding: 12px 16px; border-bottom: 1px solid #e5e7eb; background: #f9fafb; font-size: 13px; }
.builder-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.builder-label { font-weight: 600; color: #374151; }
.preset-btn, .mode-btn {
  padding: 3px 10px; border-radius: 5px; border: 1px solid #d1d5db; background: white; font-size: 12px; cursor: pointer;
}
.preset-btn--active, .mode-btn--active { background: #2563eb; color: white; border-color: #2563eb; }
.root-chips { display: flex; flex-wrap: wrap; gap: 6px; list-style: none; padding: 0; margin: 8px 0; }
.root-chip { background: #e0e7ff; color: #3730a3; border-radius: 12px; padding: 3px 8px; font-size: 12px; display: flex; align-items: center; gap: 4px; }
.chip-remove { border: none; background: none; cursor: pointer; color: #3730a3; font-weight: 700; }
h3 { font-size: 12.5px; margin: 10px 0 4px; color: #374151; }
.render-btn { margin-top: 10px; padding: 6px 16px; background: #16a34a; color: white; border: none; border-radius: 6px; font-weight: 600; cursor: pointer; }
.render-btn:disabled { opacity: .5; cursor: not-allowed; }
</style>
