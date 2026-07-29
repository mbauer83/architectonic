<script setup lang="ts">
import { ref, watch, inject } from 'vue'
import { Effect, Exit } from 'effect'
import { modelServiceKey } from '../../keys'
import type { EntityDisplayInfo } from '../../../domain'
import EntityPickerInput from '../../components/EntityPickerInput.vue'

const props = defineProps<{
  entityId?: string
  acceptedTypes: string[]
}>()
const emit = defineEmits<{
  pick: [entityId: string | null]
}>()

const svc = inject(modelServiceKey)!
const displayName = ref<string | null>(null)
const showPicker = ref(false)

const loadName = async (id: string) => {
  const exit = await Effect.runPromiseExit(svc.getEntityDisplayItem(id))
  if (Exit.isSuccess(exit)) displayName.value = exit.value.name
}

watch(() => props.entityId, (id) => {
  displayName.value = null
  if (id) void loadName(id)
}, { immediate: true })

const onSelect = (entity: EntityDisplayInfo) => {
  showPicker.value = false
  emit('pick', entity.artifact_id)
}

const onClear = () => {
  displayName.value = null
  emit('pick', null)
}
</script>

<template>
  <div class="aep">
    <template v-if="entityId && !showPicker">
      <span class="aep-badge">
        {{ displayName ?? entityId }}
        <button
          class="aep-clear"
          type="button"
          title="Remove mapping"
          @click="onClear"
        >×</button>
      </span>
    </template>
    <template v-else-if="showPicker">
      <EntityPickerInput
        :fixed-entity-types="acceptedTypes"
        :accepted-types="new Set(acceptedTypes)"
        widenable-to="none"
        placeholder="Search entities…"
        @select="onSelect"
      />
      <button
        class="aep-cancel"
        type="button"
        @click="showPicker = false"
      >
        Cancel
      </button>
    </template>
    <template v-else>
      <button
        class="aep-map-btn"
        type="button"
        @click="showPicker = true"
      >
        Map to entity…
      </button>
    </template>
  </div>
</template>

<style scoped>
.aep { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.aep-badge {
  display: inline-flex; align-items: center; gap: 4px;
  background: #eff6ff; border: 1px solid #bfdbfe; border-radius: 12px;
  padding: 2px 8px; font-size: 11px; color: #1d4ed8; max-width: 200px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.aep-clear {
  border: none; background: none; cursor: pointer; color: #6b7280;
  padding: 0; line-height: 1; font-size: 13px; flex-shrink: 0;
}
.aep-clear:hover { color: #ef4444; }
.aep-map-btn {
  font-size: 11px; color: #6b7280; background: none; border: 1px dashed #cbd5e1;
  border-radius: 4px; padding: 2px 6px; cursor: pointer;
}
.aep-map-btn:hover { color: #2563eb; border-color: #2563eb; }
.aep-cancel {
  font-size: 11px; color: #9ca3af; background: none; border: none; cursor: pointer; padding: 2px 4px;
}
</style>
