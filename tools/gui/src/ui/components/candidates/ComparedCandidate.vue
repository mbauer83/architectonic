<script setup lang="ts">
/**
 * One candidate in a comparison: its operations against the comparison's common base and the
 * diagram marked with what it changes — the candidate page's own `CandidateOperations` and
 * `MarkedCanvas`, read with the base fixed. An element another compared candidate changes as well
 * says so on its mark; a row selected here frames its element on this candidate's picture, and an element
 * pressed there selects its rows. The picture draws the candidate as it composes (`useComposedDrawing`).
 */
import { computed, inject, ref } from 'vue'
import { stableEntityId } from '../../../domain/artifactId'
import type { Marks } from '../../../domain/candidates/elementMarks'
import { diffMarks, framedMarks } from '../../../domain/candidates/elementMarks'
import { withOthers } from '../../../domain/candidates/candidateComparison'
import type { Candidates } from '../../composables/useCandidates'
import { useComposedDrawing } from '../../composables/useComposedDrawing'
import { modelServiceKey } from '../../keys'
import { candidateDetailRoute } from '../../router/artifactRoutes'
import CandidateOperations from './CandidateOperations.vue'
import CandidateResiduality from './CandidateResiduality.vue'
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
/** The picture with this candidate drawn as it composes. */
const { drawing, composing } = useComposedDrawing(inject(modelServiceKey)!, () => props.reading.comparison.value)
const marks = computed((): Marks => new Map([
  ...withOthers(diffMarks(props.reading.comparison.value), props.others, props.nameOfSet),
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
    <CandidateResiduality :candidate-id="id" />
    <div class="card">
      <CandidateOperations
        :candidates="reading"
        role="candidate architecture"
        :name-of="nameOf"
        fixed
        :framed="framed"
        @frame="framed = $event && stableEntityId($event)"
      />
    </div>
    <MarkedCanvas
      :diagram-id="diagramId"
      :drawing="drawing"
      :composing="composing"
      :marks="marks"
      hint="Select a row to frame its element, or an element to find its rows · Scroll to zoom · Drag to pan"
      empty-text="No diagram to draw: choose one above."
      @pick="framed = framed === $event ? null : $event"
    />
  </section>
</template>

<style scoped>
.compared { display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.pane-acts { display: flex; gap: 10px; align-items: center; justify-content: flex-end; font-size: 12px; }
.pane-acts a { color: var(--accent-strong); text-decoration: none; font-weight: 600; }
.pane-acts a:hover { text-decoration: underline; }
</style>
