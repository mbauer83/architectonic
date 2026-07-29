<script lang="ts">
// Name export required for recursive template self-reference
export default { name: 'ActivityStepItem' }
</script>

<script setup lang="ts">
import { computed } from 'vue'
import ActivityEntityPicker from './ActivityEntityPicker.vue'
import NoteSection from './NoteSection.vue'
import type { StepNote } from './activityElementMapping'

type Lane = { id: string; label: string }
type StepType = 'action' | 'decision' | 'fork' | 'partition'
type Step = { type: string; id: string; [key: string]: unknown }

const ACTION_TYPES: string[] = ['process', 'function']
const DECISION_TYPES: string[] = ['process', 'function', 'or-junction']
const FORK_TYPES: string[] = ['and-junction']

const props = defineProps<{
  step: Step
  lanes: Lane[]
  depth: number
}>()
const emit = defineEmits<{
  update: [step: Step]
  remove: []
}>()

const patch = (partial: Partial<Step>) => emit('update', { ...props.step, ...partial })
const defaultLaneId = computed(() => props.lanes[0]?.id)
const stepNote = (): StepNote | null => {
  const n = props.step.note
  return n && typeof n === 'object' ? (n as StepNote) : null
}
const setNote = (note: StepNote | null) => patch({ note: note ?? undefined })

const makeStep = (type: StepType): Step => {
  const id = `${type}-${Date.now().toString(36)}`
  if (type === 'decision') {
    return {
      type, id, condition: '', lane_id: defaultLaneId.value, then_label: 'yes', else_label: 'no', then_steps: [], else_steps: [],
    }
  }
  if (type === 'fork') return { type, id, branches: [[], []], lane_id: defaultLaneId.value }
  if (type === 'partition') return { type, id, label: '', steps: [] }
  return { type, id, label: '', lane_id: defaultLaneId.value }
}

// ── Decision branch helpers ────────────────────────────────────────────────────

const updateBranchStep = (key: 'then_steps' | 'else_steps', i: number, s: Step) => {
  const b = [...((props.step[key] as Step[]) ?? [])]
  b[i] = s
  patch({ [key]: b })
}
const removeBranchStep = (key: 'then_steps' | 'else_steps', i: number) =>
  patch({ [key]: ((props.step[key] as Step[]) ?? []).filter((_, j) => j !== i) })
const addBranchStep = (key: 'then_steps' | 'else_steps', type: StepType) =>
  patch({ [key]: [...((props.step[key] as Step[]) ?? []), makeStep(type)] })

// ── Fork helpers ───────────────────────────────────────────────────────────────

const updateForkStep = (bi: number, si: number, s: Step) =>
  patch({ branches: (props.step.branches as Step[][]).map((b, i) => i === bi ? b.map((x, j) => j === si ? s : x) : b) })
const removeForkStep = (bi: number, si: number) =>
  patch({ branches: (props.step.branches as Step[][]).map((b, i) => i === bi ? b.filter((_, j) => j !== si) : b) })
const addForkStep = (bi: number, type: StepType) =>
  patch({ branches: (props.step.branches as Step[][]).map((b, i) => i === bi ? [...b, makeStep(type)] : b) })
const addForkBranch = () => patch({ branches: [...((props.step.branches as Step[][]) ?? []), []] })
const removeForkBranch = (i: number) =>
  patch({ branches: ((props.step.branches as Step[][]) ?? []).filter((_, bi) => bi !== i) })

// ── Partition helpers ──────────────────────────────────────────────────────────

const updatePartStep = (i: number, s: Step) =>
  patch({ steps: ((props.step.steps as Step[]) ?? []).map((x, j) => j === i ? s : x) })
const removePartStep = (i: number) =>
  patch({ steps: ((props.step.steps as Step[]) ?? []).filter((_, j) => j !== i) })
const addPartStep = (type: StepType) =>
  patch({ steps: [...((props.step.steps as Step[]) ?? []), makeStep(type)] })
</script>

<template>
  <div :class="['step-item', `step-${step.type}`]">
    <!-- ── action ──────────────────────────────────────────────────────────── -->
    <template v-if="step.type === 'action'">
      <div class="action-row">
        <input
          class="inp label-inp"
          placeholder="Action label"
          :value="String(step.label ?? '')"
          @input="patch({ label: ($event.target as HTMLInputElement).value })"
        >
        <select
          class="inp lane-sel"
          :value="String(step.lane_id ?? '')"
          @change="patch({ lane_id: ($event.target as HTMLSelectElement).value || undefined })"
        >
          <option value="">
            No lane
          </option>
          <option
            v-for="l in lanes"
            :key="l.id"
            :value="l.id"
          >
            {{ l.label }}
          </option>
        </select>
      </div>
      <input
        class="inp link-inp"
        placeholder="Link URL (optional)"
        :value="String(step.link ?? '')"
        @input="patch({ link: ($event.target as HTMLInputElement).value || undefined })"
      >
      <NoteSection
        :note="stepNote()"
        @update="setNote"
      />
      <ActivityEntityPicker
        :entity-id="String(step.entity_id ?? '')"
        :accepted-types="ACTION_TYPES"
        @pick="patch({ entity_id: $event ?? undefined })"
      />
    </template>

    <!-- ── decision ───────────────────────────────────────────────────────── -->
    <template v-else-if="step.type === 'decision'">
      <div class="decision-header">
        <input
          class="inp cond-inp"
          placeholder="Condition"
          :value="String(step.condition ?? '')"
          @input="patch({ condition: ($event.target as HTMLInputElement).value })"
        >
        <select
          class="inp lane-sel"
          :value="String(step.lane_id ?? '')"
          @change="patch({ lane_id: ($event.target as HTMLSelectElement).value || undefined })"
        >
          <option value="">
            No lane
          </option>
          <option
            v-for="l in lanes"
            :key="l.id"
            :value="l.id"
          >
            {{ l.label }}
          </option>
        </select>
      </div>
      <ActivityEntityPicker
        :entity-id="String(step.entity_id ?? '')"
        :accepted-types="DECISION_TYPES"
        @pick="patch({ entity_id: $event ?? undefined })"
      />
      <NoteSection
        :note="stepNote()"
        @update="setNote"
      />
      <div class="branch">
        <div class="branch-hdr">
          <span class="branch-lbl">then</span>
          <input
            class="inp branch-lbl-inp"
            placeholder="then label"
            :value="String(step.then_label ?? 'yes')"
            @input="patch({ then_label: ($event.target as HTMLInputElement).value })"
          >
        </div>
        <ActivityStepItem
          v-for="(s, i) in (step.then_steps as Step[] ?? [])"
          :key="(s as Step).id"
          :step="s as Step"
          :lanes="lanes"
          :depth="depth + 1"
          @update="updateBranchStep('then_steps', i, $event)"
          @remove="removeBranchStep('then_steps', i)"
        />
        <div class="add-row">
          <button
            class="add-btn"
            type="button"
            @click="addBranchStep('then_steps', 'action')"
          >
            + Action
          </button>
          <button
            class="add-btn"
            type="button"
            @click="addBranchStep('then_steps', 'decision')"
          >
            + Decision
          </button>
          <button
            class="add-btn"
            type="button"
            @click="addBranchStep('then_steps', 'fork')"
          >
            + Fork
          </button>
          <button
            class="add-btn"
            type="button"
            @click="addBranchStep('then_steps', 'partition')"
          >
            + Partition
          </button>
        </div>
      </div>
      <div class="branch">
        <div class="branch-hdr">
          <span class="branch-lbl">else</span>
          <input
            class="inp branch-lbl-inp"
            placeholder="else label"
            :value="String(step.else_label ?? 'no')"
            @input="patch({ else_label: ($event.target as HTMLInputElement).value })"
          >
        </div>
        <ActivityStepItem
          v-for="(s, i) in (step.else_steps as Step[] ?? [])"
          :key="(s as Step).id"
          :step="s as Step"
          :lanes="lanes"
          :depth="depth + 1"
          @update="updateBranchStep('else_steps', i, $event)"
          @remove="removeBranchStep('else_steps', i)"
        />
        <div class="add-row">
          <button
            class="add-btn"
            type="button"
            @click="addBranchStep('else_steps', 'action')"
          >
            + Action
          </button>
          <button
            class="add-btn"
            type="button"
            @click="addBranchStep('else_steps', 'decision')"
          >
            + Decision
          </button>
          <button
            class="add-btn"
            type="button"
            @click="addBranchStep('else_steps', 'fork')"
          >
            + Fork
          </button>
          <button
            class="add-btn"
            type="button"
            @click="addBranchStep('else_steps', 'partition')"
          >
            + Partition
          </button>
        </div>
      </div>
    </template>

    <!-- ── fork ───────────────────────────────────────────────────────────── -->
    <template v-else-if="step.type === 'fork'">
      <ActivityEntityPicker
        :entity-id="String(step.entity_id ?? '')"
        :accepted-types="FORK_TYPES"
        @pick="patch({ entity_id: $event ?? undefined })"
      />
      <NoteSection
        :note="stepNote()"
        @update="setNote"
      />
      <div
        v-for="(branch, bi) in (step.branches as Step[][])"
        :key="bi"
        class="branch"
      >
        <div class="branch-hdr">
          <span class="branch-lbl">Branch {{ bi + 1 }}</span>
          <button
            v-if="(step.branches as Step[][]).length > 2"
            class="mini-btn"
            type="button"
            @click="removeForkBranch(bi)"
          >
            ×
          </button>
        </div>
        <ActivityStepItem
          v-for="(s, si) in branch"
          :key="(s as Step).id"
          :step="s as Step"
          :lanes="lanes"
          :depth="depth + 1"
          @update="updateForkStep(bi, si, $event)"
          @remove="removeForkStep(bi, si)"
        />
        <div class="add-row">
          <button
            class="add-btn"
            type="button"
            @click="addForkStep(bi, 'action')"
          >
            + Action
          </button>
          <button
            class="add-btn"
            type="button"
            @click="addForkStep(bi, 'decision')"
          >
            + Decision
          </button>
          <button
            class="add-btn"
            type="button"
            @click="addForkStep(bi, 'fork')"
          >
            + Fork
          </button>
          <button
            class="add-btn"
            type="button"
            @click="addForkStep(bi, 'partition')"
          >
            + Partition
          </button>
        </div>
      </div>
      <button
        class="mini-btn"
        type="button"
        @click="addForkBranch"
      >
        + Branch
      </button>
    </template>

    <!-- ── partition ──────────────────────────────────────────────────────── -->
    <template v-else-if="step.type === 'partition'">
      <input
        class="inp label-inp"
        placeholder="Partition label"
        :value="String(step.label ?? '')"
        @input="patch({ label: ($event.target as HTMLInputElement).value })"
      >
      <NoteSection
        :note="stepNote()"
        @update="setNote"
      />
      <ActivityStepItem
        v-for="(s, i) in (step.steps as Step[] ?? [])"
        :key="(s as Step).id"
        :step="s as Step"
        :lanes="lanes"
        :depth="depth + 1"
        @update="updatePartStep(i, $event)"
        @remove="removePartStep(i)"
      />
      <div class="add-row">
        <button
          class="add-btn"
          type="button"
          @click="addPartStep('action')"
        >
          + Action
        </button>
        <button
          class="add-btn"
          type="button"
          @click="addPartStep('decision')"
        >
          + Decision
        </button>
        <button
          class="add-btn"
          type="button"
          @click="addPartStep('fork')"
        >
          + Fork
        </button>
        <button
          class="add-btn"
          type="button"
          @click="addPartStep('partition')"
        >
          + Partition
        </button>
      </div>
    </template>

    <button
      class="mini-btn remove-btn"
      type="button"
      @click="emit('remove')"
    >
      ×
    </button>
  </div>
</template>

<style scoped>
.step-item {
  display: flex; flex-direction: column; gap: 6px;
  padding: 6px 8px; border-radius: 6px; border: 1px solid #e2e8f0;
  background: #fafafa; position: relative;
}
.step-action    { background: #f0f9ff; border-color: #bae6fd; }
.step-decision  { background: #fefce8; border-color: #fde68a; }
.step-fork      { background: #f0fdf4; border-color: #bbf7d0; }
.step-partition { background: #f5f3ff; border-color: #ddd6fe; }

.inp { padding: 4px 6px; border: 1px solid #cbd5e1; border-radius: 4px; font-size: 13px; box-sizing: border-box; }
.action-row   { display: flex; gap: 6px; }
.label-inp    { flex: 1 1 140px; min-width: 0; }
.link-inp     { width: 100%; }
.cond-inp     { flex: 1 1 140px; min-width: 0; }
.lane-sel     { flex: 0 1 110px; }

.decision-header { display: flex; gap: 6px; }
.branch {
  display: flex; flex-direction: column; gap: 4px;
  padding: 6px; border: 1px solid #e2e8f0; border-radius: 4px;
  background: rgba(255,255,255,0.6);
}
.branch-hdr { display: flex; align-items: center; gap: 6px; }
.branch-lbl { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: #94a3b8; white-space: nowrap; }
.branch-lbl-inp { flex: 1; min-width: 0; }

.add-row { display: flex; gap: 4px; flex-wrap: wrap; margin-top: 2px; }
.add-btn { padding: 2px 7px; border: 1px solid #cbd5e1; background: #fff; border-radius: 6px; cursor: pointer; font-size: 11px; }
.mini-btn { min-width: 28px; height: 28px; border: 1px solid #cbd5e1; background: #fff; border-radius: 6px; cursor: pointer; font-size: 13px; }
.remove-btn { position: absolute; top: 4px; right: 4px; }
</style>
