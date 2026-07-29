<script setup lang="ts">
import type { Grouping, Message, Operand } from './useSequenceModel'

const KIND_OPTIONS = ['alt', 'opt', 'loop', 'par', 'break', 'critical', 'group'] as const

const props = defineProps<{
  groupings: Grouping[]
  messages: Message[]
}>()
const emit = defineEmits<{
  add: []
  remove: [id: string]
  update: [{ id: string; patch: Partial<Grouping> }]
}>()

function msgLabel(msgId: string) {
  const idx = props.messages.findIndex((m) => m.id === msgId)
  const m = props.messages[idx]
  return m ? `${idx + 1}. ${m.label || '(unlabelled)'}` : msgId
}

function addOperand(g: Grouping) {
  const last = props.messages[props.messages.length - 1]
  if (!last) return
  const ops: Operand[] = [...g.operands, { start_message_id: last.id, end_message_id: last.id }]
  emit('update', { id: g.id, patch: { operands: ops } })
}

function removeOperand(g: Grouping, i: number) {
  if (g.operands.length <= 1) return
  const ops = g.operands.filter((_, idx) => idx !== i)
  emit('update', { id: g.id, patch: { operands: ops } })
}

function patchOperand(g: Grouping, i: number, patch: Partial<Operand>) {
  const ops = g.operands.map((op, idx) => idx === i ? { ...op, ...patch } : op)
  emit('update', { id: g.id, patch: { operands: ops } })
}

function needsLabel(kind: string) {
  return kind === 'group' || kind === 'loop'
}
</script>

<template>
  <section class="grp-editor">
    <div class="grp-header">
      <span>Groupings</span>
      <button
        class="mini-btn"
        type="button"
        :disabled="messages.length === 0"
        @click="emit('add')"
      >
        +
      </button>
    </div>
    <p
      v-if="groupings.length === 0"
      class="list-hint"
    >
      Add groupings to wrap message spans in alt/opt/loop/par blocks.
    </p>
    <div
      v-for="g in groupings"
      :key="g.id"
      class="grp-card"
    >
      <div class="grp-card-top">
        <select
          class="inp kind-sel"
          :value="g.kind"
          @change="emit('update', { id: g.id, patch: { kind: ($event.target as HTMLSelectElement).value as Grouping['kind'] } })"
        >
          <option
            v-for="k in KIND_OPTIONS"
            :key="k"
            :value="k"
          >
            {{ k }}
          </option>
        </select>
        <input
          v-if="needsLabel(g.kind)"
          class="inp label-inp"
          :value="g.label || ''"
          :placeholder="g.kind === 'group' ? 'group label' : 'loop condition'"
          @input="emit('update', { id: g.id, patch: { label: ($event.target as HTMLInputElement).value } })"
        >
        <button
          class="mini-btn rm-btn"
          type="button"
          title="Remove grouping"
          @click="emit('remove', g.id)"
        >
          ×
        </button>
      </div>
      <div class="operands">
        <div
          v-for="(op, i) in g.operands"
          :key="i"
          class="operand-row"
        >
          <span class="op-label">{{ i === 0 ? (g.kind === 'alt' ? 'if' : 'do') : (g.kind === 'par' ? 'also' : 'else') }}</span>
          <input
            v-if="g.kind === 'alt' || g.kind === 'par'"
            class="inp guard-inp"
            :value="op.guard || ''"
            placeholder="guard…"
            @input="patchOperand(g, i, { guard: ($event.target as HTMLInputElement).value })"
          >
          <select
            class="inp span-sel"
            :value="op.start_message_id"
            @change="patchOperand(g, i, { start_message_id: ($event.target as HTMLSelectElement).value })"
          >
            <option
              v-for="m in messages"
              :key="m.id"
              :value="m.id"
            >
              {{ msgLabel(m.id) }}
            </option>
          </select>
          <span class="op-to">→</span>
          <select
            class="inp span-sel"
            :value="op.end_message_id"
            @change="patchOperand(g, i, { end_message_id: ($event.target as HTMLSelectElement).value })"
          >
            <option
              v-for="m in messages"
              :key="m.id"
              :value="m.id"
            >
              {{ msgLabel(m.id) }}
            </option>
          </select>
          <button
            v-if="g.operands.length > 1"
            class="mini-btn"
            type="button"
            title="Remove operand"
            @click="removeOperand(g, i)"
          >
            −
          </button>
        </div>
        <button
          v-if="g.kind === 'alt' || g.kind === 'par'"
          class="add-op-btn"
          type="button"
          @click="addOperand(g)"
        >
          + Add {{ g.kind === 'alt' ? 'else' : 'parallel flow' }}
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.grp-editor { display: flex; flex-direction: column; gap: 8px; }
.grp-header { display: flex; align-items: center; justify-content: space-between; font-weight: 650; font-size: 12px; }
.list-hint { font-size: 12px; color: #9ca3af; margin: 0; }
.grp-card { display: flex; flex-direction: column; gap: 6px; padding: 8px 10px; border: 1px solid #dbe3ef; border-radius: 8px; background: #fff; }
.grp-card-top { display: flex; align-items: center; gap: 6px; }
.kind-sel { width: 90px; }
.label-inp { flex: 1; }
.rm-btn { flex-shrink: 0; }
.operands { display: flex; flex-direction: column; gap: 4px; padding-left: 4px; }
.operand-row { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.op-label { font-size: 11px; font-weight: 600; color: #6366f1; width: 28px; flex-shrink: 0; }
.op-to { font-size: 11px; color: #94a3b8; }
.guard-inp { width: 80px; }
.span-sel { width: 130px; }
.add-op-btn { align-self: flex-start; font-size: 11px; color: #6366f1; background: none; border: 1px dashed #c7d2fe; border-radius: 4px; padding: 2px 8px; cursor: pointer; }
.add-op-btn:hover { background: #eef2ff; }
.mini-btn { min-width: 24px; height: 24px; border: 1px solid #cbd5e1; background: #fff; border-radius: 5px; cursor: pointer; font-size: 14px; color: #374151; }
.mini-btn:disabled { opacity: .45; cursor: not-allowed; }
.inp {
  padding: 4px 6px; border: 1px solid #cbd5e1; border-radius: 5px;
  font-size: 12px; background: white; color: #1e293b; outline: none; box-sizing: border-box;
}
.inp:focus { border-color: #3b82f6; box-shadow: 0 0 0 2px #bfdbfe; }
</style>
