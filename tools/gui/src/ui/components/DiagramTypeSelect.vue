<script setup lang="ts">
import { inject, onMounted, ref, watch } from 'vue'
import { Effect } from 'effect'
import { modelServiceKey } from '../keys'
import type { DiagramTypeSummary } from '../../domain'

const props = defineProps<{ modelValue: string }>()
const emit = defineEmits<{
  'update:modelValue': [value: string]
  select: [summary: DiagramTypeSummary]
}>()

const svc = inject(modelServiceKey)!
const kinds = ref<DiagramTypeSummary[]>([])
const busy = ref(false)

const load = async () => {
  busy.value = true
  kinds.value = await Effect.runPromise(svc.listDiagramTypes()).catch(() => [])
  busy.value = false
  const selected = kinds.value.find((kind) => kind.key === props.modelValue) ?? kinds.value[0]
  if (selected) {
    if (selected.key !== props.modelValue) emit('update:modelValue', selected.key)
    emit('select', selected)
  }
}

watch(() => props.modelValue, (value) => {
  const selected = kinds.value.find((kind) => kind.key === value)
  if (selected) emit('select', selected)
})

onMounted(load)
</script>

<template>
  <select
    class="inp"
    :value="modelValue"
    :disabled="busy"
    @change="emit('update:modelValue', ($event.target as HTMLSelectElement).value)"
  >
    <option
      v-for="kind in kinds"
      :key="kind.key"
      :value="kind.key"
    >
      {{ kind.label }}
    </option>
  </select>
</template>
