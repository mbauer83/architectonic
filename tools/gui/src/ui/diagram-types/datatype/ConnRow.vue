<script setup lang="ts">
import { computed, inject, ref } from 'vue'
import { Effect, Exit } from 'effect'
import type { Classifier, DtConn, DtConnType, GeneralizationSet } from './useDatatypeModel'
import { DT_CONN_TYPES } from './useDatatypeModel'
import { useDtBackingConstraint } from './useDtBackingConstraint'
import { modelServiceKey } from '../../keys'
import DatatypeNoteSection from './DatatypeNoteSection.vue'

const props = defineProps<{
  conn: DtConn
  classifiers: Classifier[]
  generalizationSets: GeneralizationSet[]
}>()
const emit = defineEmits<{
  removeConn: [id: string]
  updateConn: [id: string, patch: Partial<DtConn>]
}>()

const svc = inject(modelServiceKey)!
const clsById = computed(() => Object.fromEntries(props.classifiers.map((c) => [c.id, c])))
const srcDob = computed(() => clsById.value[props.conn.source]?.entity_id)
const tgtDob = computed(() => clsById.value[props.conn.target]?.entity_id)
const bothBound = computed(() => !!srcDob.value && !!tgtDob.value)
const needsBacking = computed(() => bothBound.value && !props.conn.backing_conn_id)

const constraint = useDtBackingConstraint(() => srcDob.value, () => tgtDob.value)

const admissibleTypes = computed((): DtConnType[] => {
  if (!bothBound.value) return [...DT_CONN_TYPES]
  return constraint.admissibleTypes() ?? [...DT_CONN_TYPES]
})

function onTypeChange(newType: DtConnType) {
  if (bothBound.value) {
    const backing = constraint.backingConnectionFor(newType, srcDob.value, tgtDob.value)
    emit('updateConn', props.conn.id, { conn_type: newType, backing_conn_id: backing?.artifact_id })
  } else {
    emit('updateConn', props.conn.id, { conn_type: newType })
  }
}

const fixing = ref(false)
const fixError = ref<string | null>(null)

async function applyFix() {
  const src = srcDob.value
  const tgt = tgtDob.value
  if (!src || !tgt) return
  fixing.value = true
  fixError.value = null
  try {
    const existing = constraint.backingConnectionFor(props.conn.conn_type, src, tgt)
    if (existing) {
      emit('updateConn', props.conn.id, { backing_conn_id: existing.artifact_id })
      return
    }
    const preferred = constraint.preferredBackingType(props.conn.conn_type)
    if (!preferred) {
      fixError.value = 'No admissible backing type found'
      return
    }
    const exit = await Effect.runPromiseExit(
      svc.addConnection({ source_entity: src, connection_type: preferred, target_entity: tgt }),
    )
    if (Exit.isSuccess(exit)) {
      emit('updateConn', props.conn.id, { backing_conn_id: exit.value.artifact_id })
    } else {
      fixError.value = 'Failed to create backing connection'
    }
  } finally {
    fixing.value = false
  }
}
</script>

<template>
  <div class="row-wrap">
    <div class="rl-row">
      <select
        class="conn-type"
        :value="conn.conn_type"
        @change="onTypeChange(($event.target as HTMLSelectElement).value as DtConnType)"
      >
        <option
          v-for="t in admissibleTypes"
          :key="t"
          :value="t"
        >
          {{ t }}
        </option>
      </select>
      <select
        class="conn-end"
        :value="conn.source"
        @change="emit('updateConn', conn.id, { source: ($event.target as HTMLSelectElement).value })"
      >
        <option
          v-for="cls in classifiers"
          :key="cls.id"
          :value="cls.id"
        >
          {{ cls.label ?? cls.id }}
        </option>
      </select>
      <span class="rl-arrow">→</span>
      <select
        class="conn-end"
        :value="conn.target"
        @change="emit('updateConn', conn.id, { target: ($event.target as HTMLSelectElement).value })"
      >
        <option
          v-for="cls in classifiers"
          :key="cls.id"
          :value="cls.id"
        >
          {{ cls.label ?? cls.id }}
        </option>
      </select>
      <label class="field-stack">
        <span>Source multiplicity</span>
        <input
          class="mult-in"
          type="text"
          :value="conn.src_multiplicity ?? ''"
          placeholder="0..1"
          title="Source multiplicity (for example: 1, 0..1, 1..*, *)"
          @input="emit('updateConn', conn.id, { src_multiplicity: ($event.target as HTMLInputElement).value || undefined })"
        >
      </label>
      <label class="field-stack">
        <span>Target multiplicity</span>
        <input
          class="mult-in"
          type="text"
          :value="conn.tgt_multiplicity ?? ''"
          placeholder="1..*"
          title="Target multiplicity (for example: 1, 0..1, 1..*, *)"
          @input="emit('updateConn', conn.id, { tgt_multiplicity: ($event.target as HTMLInputElement).value || undefined })"
        >
      </label>
      <input
        class="lbl-in"
        type="text"
        :value="conn.label ?? ''"
        placeholder="label"
        @input="emit('updateConn', conn.id, { label: ($event.target as HTMLInputElement).value || undefined })"
      >
      <select
        v-if="conn.conn_type === 'dt-generalization'"
        class="gset-sel"
        title="Generalization set (groups cases under {covering, disjoint})"
        :value="conn.generalization_set ?? ''"
        @change="emit('updateConn', conn.id, { generalization_set: ($event.target as HTMLSelectElement).value || undefined })"
      >
        <option value="">
          (no set)
        </option>
        <option
          v-for="set in generalizationSets"
          :key="set.id"
          :value="set.id"
        >
          {{ set.label ?? set.id }}
        </option>
      </select>
      <span
        v-if="conn.backing_conn_id"
        class="binding-badge"
        :title="`Backed by model relation: ${conn.backing_conn_id}`"
      >Model relation bound</span>
      <button
        class="del-btn"
        type="button"
        @click="emit('removeConn', conn.id)"
      >
        ×
      </button>
    </div>
    <DatatypeNoteSection
      :note="conn.note"
      @update="emit('updateConn', conn.id, { note: $event })"
    />
    <div
      v-if="needsBacking"
      class="fix-row"
    >
      <span class="fix-warn">This relation needs a compatible backing model relation.</span>
      <button
        class="fix-btn"
        type="button"
        :disabled="fixing"
        @click="applyFix"
      >
        {{ fixing ? 'Creating relation…' : 'Create compatible relation & bind' }}
      </button>
      <span
        v-if="fixError"
        class="fix-err"
      >{{ fixError }}</span>
    </div>
  </div>
</template>

<style scoped>
.row-wrap { display: flex; flex-direction: column; gap: 2px; }
.rl-row { display: flex; gap: 4px; align-items: center; flex-wrap: wrap; }
.conn-type { font-size: 11px; border: 1px solid #e2e8f0; border-radius: 3px; padding: 1px 3px; background: #f8fafc; min-width: 120px; }
.conn-end { font-size: 11px; border: 1px solid #e2e8f0; border-radius: 3px; padding: 1px 3px; min-width: 80px; }
.rl-arrow { font-size: 11px; color: #6b7280; }
.mult-in { width: 52px; font-size: 11px; border: 1px solid #e2e8f0; border-radius: 3px; padding: 1px 3px; }
.field-stack { display: flex; flex-direction: column; gap: 1px; font-size: 9px; color: #6b7280; }
.lbl-in { flex: 1; min-width: 60px; font-size: 11px; border: 1px solid #e2e8f0; border-radius: 3px; padding: 1px 4px; }
.gset-sel { font-size: 11px; border: 1px solid #c7d2fe; border-radius: 3px; padding: 1px 3px; background: #eef2ff; }
.binding-badge { font-size: 12px; color: #059669; padding: 0 2px; }
.del-btn { border: none; background: none; cursor: pointer; color: #9ca3af; font-size: 14px; padding: 0 2px; flex-shrink: 0; }
.del-btn:hover { color: #ef4444; }
.fix-row { display: flex; gap: 6px; align-items: center; padding: 2px 4px; background: #fffbeb; border-left: 2px solid #f59e0b; border-radius: 0 3px 3px 0; }
.fix-warn { font-size: 10px; color: #b45309; flex: 1; }
.fix-btn { font-size: 10px; padding: 1px 8px; border: 1px solid #f59e0b; border-radius: 3px; background: #fef3c7; cursor: pointer; white-space: nowrap; }
.fix-btn:hover:not(:disabled) { background: #fde68a; }
.fix-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.fix-err { font-size: 10px; color: #dc2626; }
</style>
