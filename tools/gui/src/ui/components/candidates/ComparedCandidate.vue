<script setup lang="ts">
/**
 * One candidate in a comparison: its operations against the comparison's common base and the
 * diagram marked with what it changes — the candidate page's own `CandidateOperations` and
 * `MarkedCanvas`, read with the base fixed. An element another compared candidate changes as well
 * says so on its mark; a row selected here frames its element on this candidate's picture.
 */
import { computed, ref } from 'vue'
import { stableEntityId } from '../../../domain/artifactId'
import type { Marks } from '../../../domain/candidates/canvasMarks'
import { diffMarks, framedMarks } from '../../../domain/candidates/canvasMarks'
import { withOthers } from '../../../domain/candidates/candidateComparison'
import type { Candidates } from '../../composables/useCandidates'
import { candidateDetailRoute } from '../../router/artifactRoutes'
import CandidateOperations from './CandidateOperations.vue'
import MarkedCanvas from './MarkedCanvas.vue'

const props = defineProps<{
  id: string
  reading: Candidates
  diagramId: string
  /** The elements other compared candidates change too, with which. */
  others: ReadonlyMap<string, readonly string[]>
  /** A candidate by name. */
  nameOfSet: (id: string) => string
}>()
const emit = defineEmits<{ remove: [id: string] }>()

const framed = ref<string | null>(null)
const marks = computed((): Marks => new Map([
  ...withOthers(diffMarks(props.reading.comparison.value?.diff ?? []), props.others, props.nameOfSet),
  ...(framed.value ? framedMarks([framed.value], 'The row selected above') : new Map()),
]))
/** A name the comparison does not give: the id as it is. */
const nameOf = (id: string): string => id
</script>

<template>
  <section
    class="compared"
    :aria-label="nameOfSet(id)"
    data-testid="compared-candidate"
  >
    <div class="pane-acts">
      <RouterLink :to="candidateDetailRoute(id)">
        Open
      </RouterLink>
      <button
        type="button"
        class="btn btn-sm"
        data-testid="drop-compared"
        @click="emit('remove', id)"
      >
        Remove from the comparison
      </button>
    </div>
    <div class="card">
      <CandidateOperations
        :candidates="reading"
        role="candidate architecture"
        :name-of="nameOf"
        fixed
        @frame="framed = $event && stableEntityId($event)"
      />
    </div>
    <MarkedCanvas
      :diagram-id="diagramId"
      :drawing="reading.comparison.value?.drawing ?? null"
      :marks="marks"
      hint="Select a row to frame its element · Scroll to zoom · Drag to pan"
      empty-text="No diagram to draw: choose one above."
    />
  </section>
</template>

<style scoped>
.compared { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.pane-acts { display: flex; gap: 10px; align-items: center; justify-content: flex-end; font-size: 12px; }
.pane-acts a { color: var(--accent-strong); text-decoration: none; font-weight: 600; }
.pane-acts a:hover { text-decoration: underline; }
</style>
