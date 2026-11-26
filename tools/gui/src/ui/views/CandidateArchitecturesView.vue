<script setup lang="ts">
import { diagramsHostingCandidates } from '../composables/useDiagramTypeCapabilities'
/**
 * Candidate architectures: every proposed architecture, independent of any analysis. Each stack is
 * listed under the scope its root was started over, each candidate below what it stacks on, with its
 * state and how many operations it records. A new candidate is defined on its own canvas, so it starts
 * empty and needs only a name; what a diagram draws, or another candidate to stack on, is an optional
 * seed (owner, 2026-11-26). Deleting one asks first; the server refuses while another
 * stacks on it or an analysis starts from it, and says so. Two or more ticked are compared.
 */
import { computed, inject, onMounted, ref, shallowRef } from 'vue'
import { useRouter } from 'vue-router'
import type { DiagramSummary } from '../../domain'
import { scopeLabel } from '../../domain/candidates/candidateCatalog'
import { modelServiceKey, toastKey } from '../keys'
import { candidateCompareRoute, candidateDetailRoute } from '../router/artifactRoutes'
import { useCandidateCatalog } from '../composables/useCandidateCatalog'

type Origin = 'diagram' | 'parent' | 'empty'

const svc = inject(modelServiceKey)!
const toast = inject(toastKey, () => undefined)
const router = useRouter()
const catalog = useCandidateCatalog(svc)

const diagrams = shallowRef<readonly DiagramSummary[]>([])
const creating = ref(false)
const name = ref('')
const origin = ref<Origin>('empty')
const diagram = ref('')
const parent = ref('')
const busy = ref(false)

const all = computed(() => catalog.candidates.all.value)
/** The candidates ticked for a comparison, in the order they were ticked. */
const ticked = ref<string[]>([])
const compare = () => router.push(candidateCompareRoute(ticked.value))
const canCreate = computed(() => name.value.trim() !== '' && !busy.value
  && (origin.value !== 'diagram' || diagram.value !== '') && (origin.value !== 'parent' || parent.value !== ''))

const create = async () => {
  busy.value = true
  const scoped = origin.value === 'diagram' ? diagram.value : undefined
  const record = {
    name: name.value.trim(),
    ...(origin.value === 'parent' ? { parent: parent.value } : {}),
    ...(scoped ? { diagram: scoped } : {}),
  }
  const id = await catalog.create(record)
  busy.value = false
  if (!id) return
  creating.value = false
  name.value = ''
  await router.push({ path: candidateDetailRoute(id), query: scoped ? { diagram: scoped } : {} })
}

const remove = async (id: string, label: string) => {
  if (!window.confirm(`Delete the candidate architecture ${label}? Its operations are lost.`)) return
  if (await catalog.remove(id)) toast(`Deleted ${label}.`)
}

onMounted(async () => {
  const [hosting] = await Promise.all([diagramsHostingCandidates(svc), catalog.refresh()])
  diagrams.value = hosting
})
</script>

<template>
  <div class="workbench page">
    <div class="page-hdr">
      <h1>Candidate architectures</h1>
      <button
        type="button"
        class="btn"
        data-testid="compare-candidates"
        :disabled="ticked.length < 2"
        @click="compare"
      >
        Compare{{ ticked.length ? ` ${ticked.length}` : '' }}…
      </button>
      <button
        v-if="!creating"
        type="button"
        class="btn btn-primary"
        data-testid="new-candidate"
        @click="creating = true"
      >
        New candidate architecture…
      </button>
    </div>
    <p class="lead">
      A candidate architecture proposes changes to the model without making them. Each one records its
      operations against what it stacks on — the current model, or another candidate — and nothing
      reaches the model before it is applied.
    </p>
    <form
      v-if="creating"
      class="card new-form"
      data-testid="new-candidate-form"
      @submit.prevent="create"
    >
      <label class="fld">Name <input
        v-model="name"
        required
        autofocus
        data-testid="candidate-name"
      ></label>
      <fieldset class="origins">
        <legend>Start</legend>
        <label><input
          v-model="origin"
          type="radio"
          value="empty"
          data-testid="candidate-origin-empty"
        > empty, and define it on its canvas</label>
        <label><input
          v-model="origin"
          type="radio"
          value="diagram"
          data-testid="candidate-origin-diagram"
        > seeded with what a diagram draws</label>
        <select
          v-if="origin === 'diagram'"
          v-model="diagram"
          data-testid="candidate-diagram"
          aria-label="Diagram"
        >
          <option value="">
            choose a diagram…
          </option>
          <option
            v-for="one in diagrams"
            :key="one.artifact_id"
            :value="one.artifact_id"
          >
            {{ one.name }}
          </option>
        </select>
        <label><input
          v-model="origin"
          type="radio"
          value="parent"
          data-testid="candidate-origin-parent"
        > on top of a candidate</label>
        <select
          v-if="origin === 'parent'"
          v-model="parent"
          data-testid="candidate-parent"
          aria-label="Candidate to stack on"
        >
          <option value="">
            choose a candidate…
          </option>
          <option
            v-for="one in all"
            :key="one.id"
            :value="one.id"
          >
            {{ one.name }}
          </option>
        </select>
      </fieldset>
      <div class="acts">
        <button
          type="submit"
          class="btn btn-primary"
          :disabled="!canCreate"
          data-testid="candidate-create"
        >
          Create
        </button>
        <button
          type="button"
          class="btn"
          @click="creating = false"
        >
          Cancel
        </button>
      </div>
    </form>
    <p
      v-if="catalog.error.value"
      class="err"
      role="alert"
    >
      {{ catalog.error.value }}
    </p>
    <p
      v-if="!all.length"
      class="empty"
    >
      No candidate architecture yet.
    </p>
    <section
      v-for="(group, index) in catalog.groups.value"
      :key="index"
      class="card group"
      data-testid="candidate-group"
    >
      <h2>{{ scopeLabel(group.scope) }}</h2>
      <table class="tbl">
        <thead><tr><th class="tick" /><th>Candidate</th><th>State</th><th>Operations</th><th /></tr></thead>
        <tbody>
          <tr
            v-for="row in group.rows"
            :key="row.candidate.id"
            :data-candidate="row.candidate.id"
          >
            <td class="tick">
              <input
                v-model="ticked"
                type="checkbox"
                :value="row.candidate.id"
                :aria-label="`Compare ${row.candidate.name}`"
                data-testid="tick-candidate"
              >
            </td>
            <td>
              <span
                class="ind"
                :style="{ paddingLeft: `${Math.max(row.depth - 1, 0) * 14}px` }"
              >{{ row.depth > 0 ? '└ ' : '' }}</span>
              <RouterLink :to="candidateDetailRoute(row.candidate.id)">
                {{ row.candidate.name }}
              </RouterLink>
            </td>
            <td><span class="state">{{ row.candidate.state }}</span></td>
            <td>{{ row.candidate.operations }}</td>
            <td class="row-acts">
              <button
                type="button"
                class="btn btn-sm"
                data-testid="delete-candidate"
                @click="remove(row.candidate.id, row.candidate.name)"
              >
                Delete
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<style scoped>
.page { padding: 16px 24px; max-width: 1100px; }
.page-hdr { display: flex; gap: 14px; align-items: center; }
.page-hdr h1 { flex: 1; font-size: 20px; margin: 0; }
.lead { color: var(--muted); font-size: 12.5px; margin: 6px 0 12px; }
.err { color: var(--danger-strong); font-size: 12.5px; }
.empty { color: var(--muted); font-size: 13px; }
.new-form { display: flex; flex-direction: column; gap: 8px; padding: 10px 12px; margin-bottom: 12px; font-size: 13px; }
.new-form input, .new-form select { font: inherit; margin-left: 4px; }
.origins { display: flex; gap: 6px 14px; align-items: center; flex-wrap: wrap; border: none; padding: 0; margin: 0; }
.origins legend { color: var(--muted); font-size: 12px; padding: 0; margin-bottom: 4px; }
.acts { display: flex; gap: 8px; }
.group { margin-bottom: 12px; }
.group h2 { font-size: 13px; margin: 0; padding: 8px 10px 4px; color: var(--text-2); }
.tbl { width: 100%; border-collapse: collapse; font-size: 13px; }
.tbl th { text-align: left; font-size: 11px; text-transform: uppercase; color: var(--muted); padding: 4px 10px; }
.tbl td { padding: 6px 10px; border-top: 1px solid var(--border); vertical-align: top; }
.tbl a { color: var(--accent-strong); text-decoration: none; font-weight: 600; }
.tbl a:hover { text-decoration: underline; }
.ind { color: var(--faint); font-family: ui-monospace, monospace; }
.state { font-size: 11px; font-weight: 600; color: var(--text-2); }
.row-acts { text-align: right; }
.tbl .tick { width: 24px; padding-right: 0; }
</style>
<style src="../components/candidates/workbench.css"></style>
