<script setup lang="ts">
import { computed, ref } from 'vue'
import type { DiagramContext } from '../../domain'

const props = defineProps<{ context: DiagramContext; busy: boolean }>()
const emit = defineEmits<{ add: [id: string, name: string] }>()
const query = ref('')
const choices = computed(() => {
  const needle = query.value.trim().toLocaleLowerCase()
  return props.context.suggested_entities
    .filter(group => needle || group.hop === 1)
    .flatMap(group => group.items)
    .filter(item => item.name.toLocaleLowerCase().includes(needle) || item.artifact_id.toLowerCase().includes(needle))
})
</script>

<template>
  <section class="card member-picker" aria-label="Add from model">
    <label> Add from model
      <input v-model="query" type="search" placeholder="Search neighbours" @keydown.enter.prevent="choices[0] && emit('add', choices[0].artifact_id, choices[0].name)">
    </label>
    <p>Drag onto the diagram to add it, or focus a row and press Enter.</p>
    <button
      v-for="item in choices" :key="item.artifact_id" type="button" draggable="true" :disabled="busy"
      @dragstart="$event.dataTransfer?.setData('application/x-architectonic-entity', item.artifact_id)"
      @click="emit('add', item.artifact_id, item.name)"
    >⠿ {{ item.name }}</button>
  </section>
</template>

<style scoped>
.member-picker { display: grid; gap: .4rem; max-height: 20rem; overflow: auto; padding: .75rem; }
input { width: 100%; }
button { text-align: start; cursor: grab; }
p { margin: 0; font-size: .85em; }
</style>
