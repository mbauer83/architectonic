<script setup lang="ts">
import { diagramsHostingCandidates } from '../../composables/useDiagramTypeCapabilities'
/**
 * A convenience for a candidate that holds nothing yet: start its picture from a stored diagram, whose elements
 * it then reads over, or stack it on an existing candidate. Neither is needed — elements are found and placed
 * through the panel's search, or created on the canvas — and neither writes to the model: the candidate's own
 * record changes (`diagram` and `scope`, or `parent`), through its versioned edit. Shown only while the candidate
 * is empty: no operations, no references, nothing it is drawn on or stacks on.
 */
import { computed, inject, onMounted, ref, shallowRef } from 'vue'
import { Effect } from 'effect'
import type { DiagramSummary } from '../../../domain'
import { stableEntityId } from '../../../domain/artifactId'
import type { CandidateSummary } from '../../../domain/schemas/candidates'
import { operationsOf } from '../../../domain/candidates/candidateCanvas'
import { modelServiceKey } from '../../keys'
import { formatEffectError } from '../../lib/errors'

const props = defineProps<{ candidateId: string }>()
const emit = defineEmits<{ seeded: [] }>()
const svc = inject(modelServiceKey)!

const version = ref('')
const empty = ref(false)
const diagrams = shallowRef<readonly DiagramSummary[]>([])
const candidates = shallowRef<readonly CandidateSummary[]>([])
const busy = ref(false)
const error = ref<string | null>(null)
const others = computed(() => candidates.value.filter((one) => one.id !== props.candidateId))

const nothingIn = (record: Readonly<Record<string, unknown>>): boolean =>
  !record.diagram && !record.parent && !(Array.isArray(record.scope) && record.scope.length > 0)
  && operationsOf(record).length === 0

const read = async () => {
  const [record, hosting, open] = await Promise.all([
    Effect.runPromise(svc.readCandidate(props.candidateId)),
    diagramsHostingCandidates(svc),
    Effect.runPromise(svc.listCandidates()).catch(() => []),
  ])
  version.value = record.version
  empty.value = nothingIn(record.record)
  diagrams.value = hosting
  candidates.value = open
}

const seed = async (patch: () => Promise<Readonly<Record<string, unknown>>>) => {
  busy.value = true
  error.value = null
  try {
    await Effect.runPromise(svc.editCandidate(props.candidateId, version.value, await patch()))
    empty.value = false
    emit('seeded')
  } catch (failure) {
    error.value = formatEffectError(failure)
  } finally {
    busy.value = false
  }
}
/** The diagram's elements become what the candidate reads over, and its picture starts from the diagram. */
const fromDiagram = (id: string) => seed(async () => {
  const context = await Effect.runPromise(svc.getDiagramContext(id))
  const scope = [...new Map((context.diagram.entity_ids_used ?? []).map((one) => [stableEntityId(one), one])).values()]
  return { diagram: id, scope }
})
const onTop = (id: string) => seed(() => Promise.resolve({ parent: id }))

onMounted(read)
</script>

<template>
  <section
    v-if="empty"
    class="seed"
    aria-label="Start from"
    data-testid="candidate-seed"
  >
    <p class="lead">
      Find elements below and drag them onto the canvas, or right-click the canvas to create one. To begin
      from a picture you already have:
    </p>
    <label>A diagram
      <select
        data-testid="seed-diagram"
        :disabled="busy"
        @change="fromDiagram(($event.target as HTMLSelectElement).value)"
      >
        <option value="">choose…</option>
        <option
          v-for="one in diagrams"
          :key="one.artifact_id"
          :value="one.artifact_id"
        >{{ one.name }}</option>
      </select>
    </label>
    <label>On top of a candidate
      <select
        data-testid="seed-candidate"
        :disabled="busy"
        @change="onTop(($event.target as HTMLSelectElement).value)"
      >
        <option value="">choose…</option>
        <option
          v-for="one in others"
          :key="one.id"
          :value="one.id"
        >{{ one.name }}</option>
      </select>
    </label>
    <p
      v-if="error"
      class="err"
      role="alert"
    >
      {{ error }}
    </p>
  </section>
</template>

<style scoped>
.seed { padding: 8px 10px; border-bottom: 1px solid var(--border); font-size: 12px; color: var(--text-2); }
.lead { margin: 0 0 6px; }
label { display: block; margin: 4px 0; font-size: 11px; color: var(--muted); }
select { display: block; width: 100%; margin-top: 2px; font: inherit; font-size: 12px; }
.err { color: var(--danger-strong); margin: 4px 0 0; }
</style>
