<script setup lang="ts">
/**
 * *New candidate on top…* on a candidate's page: the button, and in its place while open, the form that
 * names the new candidate. The candidate is created stacked on this one through *candidates*; the page is
 * told its id, to open it.
 */
import { ref } from 'vue'
import type { useCandidates } from '../../composables/useCandidates'

const props = defineProps<{ candidates: ReturnType<typeof useCandidates>; candidateId: string; name: string }>()
const emit = defineEmits<{ stacked: [id: string] }>()

const open = ref(false)
const stackName = ref('')
const stackOn = async () => {
  const id = await props.candidates.stackOn(props.candidateId, stackName.value.trim())
  if (!id) return
  open.value = false
  stackName.value = ''
  emit('stacked', id)
}
</script>

<template>
  <button
    v-if="!open"
    type="button"
    class="btn btn-sm"
    data-testid="stack-candidate"
    @click="open = true"
  >
    New candidate on top…
  </button>
  <form
    v-else
    class="stack-form"
    @submit.prevent="stackOn"
  >
    <label>Name <input
      v-model="stackName"
      required
      autofocus
    ></label>
    <button
      type="submit"
      class="btn btn-sm btn-primary"
      :disabled="!stackName.trim()"
    >
      Stack on {{ name }}
    </button>
    <button
      type="button"
      class="btn btn-sm"
      @click="open = false"
    >
      Cancel
    </button>
  </form>
</template>

<style scoped>
.stack-form { display: flex; gap: 8px; align-items: center; font-size: 12.5px; }
.stack-form input { font: inherit; margin-left: 4px; }
</style>
