<script setup lang="ts">
import { computed } from 'vue'
import type { DiagramTypeUiConfig, EntityDisplayInfo } from '../../../domain'
import ActivityStepItem from './ActivityStepItem.vue'

type Lane = { id: string; label: string }
type Step = { type: string; id: string; [key: string]: unknown }
type LocalConn = { id: string; conn_type: string; source: string; target: string }

const STEP_KEYS = ['action', 'decision', 'fork', 'partition'] as const
type StepKey = (typeof STEP_KEYS)[number]

const props = defineProps<{
  uiConfig: DiagramTypeUiConfig
  diagramEntities: Record<string, unknown>
  entities: EntityDisplayInfo[]
}>()
const emit = defineEmits<{ diagramEntitiesChange: [patch: Record<string, unknown>] }>()

// ── Rich ↔ flat translation ────────────────────────────────────────────────

function getConns(data: Record<string, unknown>): LocalConn[] {
  const c = data._connections
  return Array.isArray(c) ? (c as LocalConn[]) : []
}

function buildSingleTarget(kcs: LocalConn[], connType: string): Map<string, string> {
  const m = new Map<string, string>()
  for (const kc of kcs) if (kc.conn_type === connType && kc.source && kc.target) m.set(kc.source, kc.target)
  return m
}

function buildMultiTarget(kcs: LocalConn[], connType: string): Map<string, string[]> {
  const m = new Map<string, string[]>()
  for (const kc of kcs) {
    if (kc.conn_type === connType && kc.source && kc.target) {
      const list = m.get(kc.source) ?? []
      list.push(kc.target)
      m.set(kc.source, list)
    }
  }
  return m
}

function flatToRich(data: Record<string, unknown>): { lanes: Lane[]; steps: Step[] } {
  const kcs = getConns(data)
  const stepById = new Map<string, Step>()
  for (const key of STEP_KEYS) {
    const arr = data[key]
    if (Array.isArray(arr))
      for (const item of arr)
        if (item && typeof item === 'object' && (item as Step).id)
          stepById.set((item as Step).id, { ...(item as Step), type: (item as Step).type || key })
  }

  const flowNext = buildSingleTarget(kcs, 'step-flow')
  const thenFirst = buildSingleTarget(kcs, 'step-then')
  const elseFirst = buildSingleTarget(kcs, 'step-else')
  const forkBranches = buildMultiTarget(kcs, 'step-fork-branch')
  const containsFirst = buildSingleTarget(kcs, 'step-contains')
  const laneIdx = buildSingleTarget(kcs, 'step-in-lane')
  const noteByStep = new Map<string, { side: string; text: string }>()
  const noteById = new Map<string, { side: string; text: string }>()
  const rawNotes = data.note
  if (Array.isArray(rawNotes))
    for (const n of rawNotes as Step[])
      if (n.id) noteById.set(String(n.id), {
        side: typeof n.side === 'string' ? n.side : 'right',
        text: typeof n.text === 'string' ? n.text : '',
      })
  for (const kc of kcs)
    if (kc.conn_type === 'step-note-of' && kc.source && kc.target && noteById.has(kc.source))
      noteByStep.set(kc.target, noteById.get(kc.source)!)

  const branchEntries = new Set<string>([
    ...thenFirst.values(), ...elseFirst.values(), ...containsFirst.values(),
    ...[...forkBranches.values()].flat(),
  ])
  const branchOwned = new Set(branchEntries)
  let changed = true
  while (changed) {
    changed = false
    for (const [src, tgt] of flowNext) if (branchOwned.has(src) && !branchOwned.has(tgt)) { branchOwned.add(tgt); changed = true }
  }

  const enrich = (step: Step): Step => {
    const r: Step = { ...step }
    const laneId = laneIdx.get(step.id)
    if (laneId) r.lane_id = laneId
    const note = noteByStep.get(step.id)
    if (note) r.note = note
    if (step.type === 'decision') {
      r.then_steps = buildChain(thenFirst.get(step.id))
      r.else_steps = buildChain(elseFirst.get(step.id))
    }
    if (step.type === 'fork') r.branches = (forkBranches.get(step.id) ?? []).map(id => buildChain(id))
    if (step.type === 'partition') r.steps = buildChain(containsFirst.get(step.id))
    return r
  }

  const buildChain = (startId: string | undefined): Step[] => {
    const result: Step[] = []
    let id: string | undefined = startId
    const seen = new Set<string>()
    while (id && !seen.has(id)) {
      seen.add(id)
      const s = stepById.get(id)
      if (!s) break
      result.push(enrich(s))
      id = flowNext.get(id)
    }
    return result
  }

  const hasIncomingFlow = new Set(flowNext.values())
  const root = [...stepById.keys()].find(id => !branchOwned.has(id) && !hasIncomingFlow.has(id))
  const topLevelSteps = root ? buildChain(root) : STEP_KEYS.flatMap(key => {
    const arr = data[key]
    return Array.isArray(arr)
      ? (arr as Step[]).filter(s => s?.id && !branchOwned.has(String(s.id))).map(s => enrich({ ...s, type: s.type || key }))
      : []
  })

  const lanes = Array.isArray(data.swimlane)
    ? (data.swimlane as Lane[]).filter(l => l && l.id)
    : []
  return { lanes, steps: topLevelSteps }
}

function richToFlat(lanes: Lane[], richSteps: Step[], existingConns: LocalConn[]): Record<string, unknown> {
  const entities: Record<string, Step[]> = {}
  const conns: LocalConn[] = []
  let seq = Date.now()
  const mkId = () => `c-${(seq++).toString(36)}`

  const addConn = (conn_type: string, source: string, target: string) =>
    conns.push({ id: mkId(), conn_type, source, target })

  const flattenStep = (step: Step) => {
    const key = (step.type as StepKey) || 'action'
    if (!entities[key]) entities[key] = []
    const flat: Step = { type: step.type, id: step.id }
    for (const [k, v] of Object.entries(step))
      if (!['then_steps', 'else_steps', 'branches', 'steps', 'lane_id', 'note', '_sourceKey'].includes(k))
        flat[k] = v
    entities[key].push(flat)
    if (typeof step.lane_id === 'string' && step.lane_id) addConn('step-in-lane', step.id, step.lane_id)
    if (step.note && typeof step.note === 'object') {
      const n = step.note as { side?: string; text?: string }
      const noteId = `note-${step.id}`
      if (!entities.note) entities.note = []
      entities.note.push({ type: 'note', id: noteId, side: n.side ?? 'right', text: n.text ?? '' })
      addConn('step-note-of', noteId, step.id)
    }
    if (step.type === 'decision') {
      flattenBranch(step.id, 'step-then', (step.then_steps as Step[] | undefined) ?? [])
      flattenBranch(step.id, 'step-else', (step.else_steps as Step[] | undefined) ?? [])
    }
    if (step.type === 'fork') {
      for (const branch of (step.branches as Step[][] | undefined) ?? [])
        flattenBranch(step.id, 'step-fork-branch', branch)
    }
    if (step.type === 'partition')
      flattenBranch(step.id, 'step-contains', (step.steps as Step[] | undefined) ?? [])
  }

  const flattenBranch = (parentId: string, entryConnType: string, steps: Step[]) => {
    for (let i = 0; i < steps.length; i++) {
      const connType = i === 0 ? entryConnType : 'step-flow'
      const source = i === 0 ? parentId : steps[i - 1].id
      addConn(connType, source, steps[i].id)
      flattenStep(steps[i])
    }
  }

  for (let i = 0; i < richSteps.length; i++) {
    if (i > 0) addConn('step-flow', richSteps[i - 1].id, richSteps[i].id)
    flattenStep(richSteps[i])
  }

  const structural = new Set(['step-in-lane', 'step-flow', 'step-then', 'step-else', 'step-fork-branch', 'step-contains', 'step-note-of'])
  for (const kc of existingConns)
    if (!structural.has(kc.conn_type)) conns.push(kc)

  return { swimlane: lanes, ...entities, _connections: conns }
}

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
