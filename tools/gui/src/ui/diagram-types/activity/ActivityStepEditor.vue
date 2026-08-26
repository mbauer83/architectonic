<script setup lang="ts">
import { computed } from 'vue'
import type { DiagramTypeUiConfig, EntityDisplayInfo } from '../../../domain'
import {
  flatToRich, getConns, richToFlat, type Step, type StepKey,
} from './activityStepGraph'
import ActivityStepItem from './ActivityStepItem.vue'

const props = defineProps<{
  uiConfig: DiagramTypeUiConfig
  diagramEntities: Record<string, unknown>
  entities: EntityDisplayInfo[]
}>()
const emit = defineEmits<{ diagramEntitiesChange: [patch: Record<string, unknown>] }>()

// ── Computed rich state ────────────────────────────────────────────────────

const rich = computed(() => flatToRich(props.diagramEntities))
const lanes = computed(() => rich.value.lanes)
const steps = computed(() => rich.value.steps)
const hasMinimumLanes = computed(() => lanes.value.length >= 2)
const defaultLaneId = computed(() => lanes.value[0]?.id)

// ── Mutations (same API as before — steps is the rich flat-by-type list) ──

const addStep = (type: StepKey) => {
  if (!hasMinimumLanes.value) return
  const id = `${type}-${Date.now().toString(36)}`
  const base: Step = { type, id }
  if (type === 'action') Object.assign(base, { label: '', lane_id: defaultLaneId.value })
  else if (type === 'decision')
    Object.assign(base, {
      condition: '',
      lane_id: defaultLaneId.value,
      then_label: 'yes',
      else_label: 'no',
      then_steps: [],
      else_steps: [],
    })
  else if (type === 'fork') Object.assign(base, { branches: [[], []], lane_id: defaultLaneId.value })
  else if (type === 'partition') Object.assign(base, { label: '', steps: [] })
  const newRich = [...steps.value, base]
  emit('diagramEntitiesChange', richToFlat(lanes.value, newRich, getConns(props.diagramEntities)))
}

const updateStep = (id: string, newStep: Step) => {
  const newRich = steps.value.map(s => s.id === id ? newStep : s)
  emit('diagramEntitiesChange', richToFlat(lanes.value, newRich, getConns(props.diagramEntities)))
}

const removeStep = (id: string) => {
  const newRich = steps.value.filter(s => s.id !== id)
  emit('diagramEntitiesChange', richToFlat(lanes.value, newRich, getConns(props.diagramEntities)))
}
</script>

<template>
  <section class="step-editor">
    <div class="editor-header">
      <span>Steps</span>
      <div class="add-btns">
        <button
          class="add-btn"
          :disabled="!hasMinimumLanes"
          type="button"
          @click="addStep('action')"
        >
          + Action
        </button>
        <button
          class="add-btn"
          :disabled="!hasMinimumLanes"
          type="button"
          @click="addStep('decision')"
        >
          + Decision
        </button>
        <button
          class="add-btn"
          :disabled="!hasMinimumLanes"
          type="button"
          @click="addStep('fork')"
        >
          + Fork
        </button>
        <button
          class="add-btn"
          :disabled="!hasMinimumLanes"
          type="button"
          @click="addStep('partition')"
        >
          + Partition
        </button>
      </div>
    </div>
    <p
      v-if="!hasMinimumLanes"
      class="empty-msg"
    >
      Add at least two swimlanes before defining the activity flow.
    </p>
    <p
      v-else-if="steps.length === 0"
      class="empty-msg"
    >
      Add steps to define the activity flow.
    </p>
    <ActivityStepItem
      v-for="step in steps"
      :key="step.id"
      :step="step"
      :lanes="lanes"
      :depth="0"
      @update="updateStep(step.id, $event)"
      @remove="removeStep(step.id)"
    />
  </section>
</template>

<style scoped>
.step-editor { display: flex; flex-direction: column; gap: 8px; }
.editor-header { display: flex; align-items: center; justify-content: space-between; font-weight: 650; flex-wrap: wrap; gap: 4px; }
.add-btns { display: flex; gap: 4px; flex-wrap: wrap; }
.add-btn { padding: 3px 8px; border: 1px solid #cbd5e1; background: #fff; border-radius: 6px; cursor: pointer; font-size: 12px; }
.add-btn:disabled { opacity: .45; cursor: not-allowed; }
.empty-msg { font-size: 12px; color: #9ca3af; margin: 0; }
</style>
