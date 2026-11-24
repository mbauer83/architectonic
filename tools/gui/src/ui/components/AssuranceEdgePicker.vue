<script setup lang="ts">
/**
 * Ontology-driven edge authoring: connection types come exclusively from
 * GET /api/assurance/edge-catalog filtered to the legal set for the concrete
 * node-type pair; targets come from the exposure-filtered server-side search.
 * Supports both directions (this node as source or as target).
 */
import { ref, computed, onMounted } from 'vue'
import {
  candidateProvenance, edgeSubmission, emptyLegalSetMessage, isCrossAnalysis,
  legalTypesForSelection,
  type EdgeCatalog, type EdgeDirection,
} from './AssuranceEdgePicker.helpers'
// The hit shape is the route's, decoded — it was a four-field restatement of an eight-field body.
import {
  decodeEdgeCatalog,
  decodeSearchHits,
  type AssuranceSearchHit as SearchHit,
} from '../../domain/schemas/assurance-analyses'


const props = defineProps<{
  sourceId: string
  sourceType: string
  /** The analysis this node belongs to, used only to mark a candidate as another analysis' work.
   *  It never narrows the candidate set — see the helpers' header for why that matters. */
  sourceAnalysisId?: string | null
  loading?: boolean
}>()

const emit = defineEmits<{
  submit: [data: { source_id: string; target_id: string; conn_type: string }]
  cancel: []
}>()

const catalog = ref<EdgeCatalog | null>(null)
const catalogError = ref<string | null>(null)
const direction = ref<EdgeDirection>('outgoing')
const connType = ref('')
const targetQuery = ref('')
const target = ref<SearchHit | null>(null)
const searchResults = ref<SearchHit[]>([])
const searching = ref(false)
const searchError = ref<string | null>(null)

onMounted(async () => {
  try {
    const resp = await fetch('/api/assurance/edge-catalog')
    if (!resp.ok) {
      catalogError.value = `Edge catalog unavailable (HTTP ${resp.status})`
      return
    }
    catalog.value = decodeEdgeCatalog(await resp.json())
  } catch (e) {
    catalogError.value = String(e)
  }
})

const legalTypes = computed(() => {
  if (!catalog.value || !target.value) return []
  return legalTypesForSelection(
    catalog.value, direction.value, props.sourceType, target.value.artifact_type,
  )
})

const noLegalTypes = computed(() =>
  catalog.value !== null && target.value !== null && legalTypes.value.length === 0)

const emptyMessage = computed(() => target.value === null
  ? ''
  : emptyLegalSetMessage(direction.value, props.sourceType, target.value.artifact_type))

const canSubmit = computed(() =>
  connType.value !== ''
  && target.value !== null
  && legalTypes.value.includes(connType.value)
  && !props.loading)

async function searchNodes() {
  const q = targetQuery.value.trim()
  if (!q) {
    searchResults.value = []
    return
  }
  searching.value = true
  searchError.value = null
  try {
    const resp = await fetch(`/api/assurance/search?q=${encodeURIComponent(q)}&limit=15`)
    if (!resp.ok) {
      searchError.value = resp.status === 423 ? 'Store is locked.' : `Search failed (HTTP ${resp.status})`
      return
    }
    searchResults.value = decodeSearchHits(await resp.json())
  } catch (e) {
    searchError.value = String(e)
  } finally {
    searching.value = false
  }
}

function selectTarget(hit: SearchHit) {
  target.value = hit
  targetQuery.value = `${hit.name} (${hit.artifact_type})`
  searchResults.value = []
  if (!legalTypes.value.includes(connType.value)) connType.value = ''
}

function setDirection(value: EdgeDirection) {
  direction.value = value
  if (!legalTypes.value.includes(connType.value)) connType.value = ''
}

function handleSubmit() {
  if (!canSubmit.value || !target.value) return
  emit('submit', edgeSubmission(
    direction.value, props.sourceId, target.value.artifact_id, connType.value,
  ))
}
</script>

<template>
  <form
    class="edge-picker"
    @submit.prevent="handleSubmit"
  >
    <div
      v-if="catalogError"
      class="catalog-error"
    >
      {{ catalogError }}
    </div>

    <div class="form-row">
      <label class="form-label">Direction</label>
      <div class="direction-toggle">
        <button
          type="button"
          class="direction-btn"
          :class="{ 'direction-btn--active': direction === 'outgoing' }"
          @click="setDirection('outgoing')"
        >
          Outgoing (this node →)
        </button>
        <button
          type="button"
          class="direction-btn"
          :class="{ 'direction-btn--active': direction === 'incoming' }"
          @click="setDirection('incoming')"
        >
          Incoming (→ this node)
        </button>
      </div>
    </div>

    <div class="form-row">
      <label class="form-label">{{ direction === 'outgoing' ? 'Target node' : 'Source node' }} <span class="required">*</span></label>
      <div class="search-box">
        <input
          v-model="targetQuery"
          type="text"
          class="form-control"
          placeholder="Search by name…"
          @input="searchNodes"
        >
        <div
          v-if="searching"
          class="search-hint"
        >
          Searching…
        </div>
        <div
          v-else-if="searchError"
          class="search-error"
        >
          {{ searchError }}
        </div>
        <ul
          v-else-if="searchResults.length > 0"
          class="search-results"
        >
          <li
            v-for="hit in searchResults"
            :key="hit.artifact_id"
            class="search-result-item"
            @click="selectTarget(hit)"
          >
            <span class="result-badge">{{ hit.artifact_type }}</span>
            <span class="result-name">{{ hit.name }}</span>
            <!-- Whose work this is. Shown, not filtered on: a cross-method edge is the point. -->
            <span
              v-if="candidateProvenance(hit.analysis)"
              class="result-analysis"
              :class="{ 'result-analysis--other': isCrossAnalysis(props.sourceAnalysisId, hit.analysis) }"
            >{{ candidateProvenance(hit.analysis) }}</span>
            <span class="result-id">{{ hit.artifact_id }}</span>
          </li>
        </ul>
      </div>
      <div
        v-if="target"
        class="target-selected"
      >
        Selected: <code>{{ target.artifact_id }}</code>
      </div>
    </div>

    <div class="form-row">
      <label class="form-label">Connection type <span class="required">*</span></label>
      <div
        v-if="!target"
        class="search-hint"
      >
        Select a node first — only ontology-legal types for the concrete pair are offered.
      </div>
      <div
        v-else-if="noLegalTypes"
        class="empty-legal-set"
      >
        {{ emptyMessage }}
      </div>
      <select
        v-else
        v-model="connType"
        class="form-control"
        required
      >
        <option value="">
          — select —
        </option>
        <option
          v-for="t in legalTypes"
          :key="t"
          :value="t"
        >
          {{ t }}
        </option>
      </select>
    </div>

    <div class="form-actions">
      <button
        type="submit"
        class="btn-primary"
        :disabled="!canSubmit"
      >
        {{ loading ? 'Adding…' : 'Add edge' }}
      </button>
      <button
        type="button"
        class="btn-secondary"
        @click="emit('cancel')"
      >
        Cancel
      </button>
    </div>
  </form>
</template>

<style scoped>
.edge-picker { display: flex; flex-direction: column; gap: 14px; }
.form-row { display: flex; flex-direction: column; gap: 4px; }
.form-label { font-size: 12px; font-weight: 600; color: var(--text-2); }
.required { color: var(--danger); }
.catalog-error, .empty-legal-set {
  font-size: 12px;
  color: var(--warn-text);
  background: var(--warn-soft);
  border: 1px solid var(--warn);
  border-radius: 6px;
  padding: 6px 10px;
}
.direction-toggle { display: flex; gap: 6px; }
.direction-btn {
  padding: 4px 10px;
  border: 1px solid var(--border-strong);
  border-radius: 6px;
  background: var(--surface);
  font-size: 12px;
  cursor: pointer;
  color: var(--text-2);
}
.direction-btn--active { background: var(--accent); color: var(--on-accent); border-color: var(--accent); }
.form-control {
  font-size: 13px;
  padding: 6px 10px;
  border: 1px solid var(--border-strong);
  border-radius: 6px;
  background: var(--surface);
  color: var(--text);
  width: 100%;
  box-sizing: border-box;
}
.form-control:focus { outline: 2px solid var(--accent); border-color: transparent; }
.search-box { position: relative; }
.search-hint, .search-error { font-size: 12px; color: var(--muted); padding: 4px 0; }
.search-error { color: var(--danger-strong); }
.search-results {
  list-style: none;
  margin: 4px 0 0;
  padding: 0;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--surface);
  max-height: 180px;
  overflow-y: auto;
}
.search-result-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  cursor: pointer;
  font-size: 13px;
  border-bottom: 1px solid var(--hair);
}
.search-result-item:hover { background: var(--info-soft); }
.search-result-item:last-child { border-bottom: none; }
.result-analysis { font-size: 11px; color: var(--muted); margin-left: auto; flex-shrink: 0; }
/* Another analysis' node, drawn so the author notices they are reaching across methods. */
.result-analysis--other { color: var(--warn-text); font-weight: 600; }
.result-badge {
  font-size: 10px;
  font-weight: 600;
  background: var(--type-soft);
  color: var(--accent-strong);
  padding: 1px 6px;
  border-radius: 3px;
  flex-shrink: 0;
  white-space: nowrap;
}
.result-name { flex: 1; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.result-id { font-size: 10px; color: var(--faint); white-space: nowrap; }
.target-selected { font-size: 12px; color: var(--ok-text); }
.target-selected code { font-size: 11px; background: var(--ok-soft); padding: 1px 4px; border-radius: 3px; }
.form-actions { display: flex; gap: 10px; }
.btn-primary {
  padding: 7px 18px;
  background: var(--accent);
  color: var(--on-accent);
  border: none;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.btn-primary:hover:not(:disabled) { background: var(--accent-strong); }
.btn-primary:disabled { opacity: 0.5; cursor: default; }
.btn-secondary {
  padding: 7px 18px;
  background: var(--soft);
  color: var(--text-2);
  border: 1px solid var(--border-strong);
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
}
.btn-secondary:hover { background: var(--border); }
</style>
