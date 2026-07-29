<script setup lang="ts">
import { computed, inject, onMounted, ref, watch } from 'vue'
import { Effect } from 'effect'
import { modelServiceKey } from '../keys'
import { domainOptionsForDomains, getDomainLabel } from '../lib/domains'
import { buildReferenceMarkdown } from '../lib/referenceLinks.js'
import { formatEntityTypeTerm, rankedEntityTypeSet } from '../lib/documentSections'
import type { DocumentType, ReferenceSearchHit, WriteHelp } from '../../domain'
import { readErrorMessage } from '../lib/errors'

interface Props {
  currentPath?: string
  fixedKinds?: ArtifactKind[]
  sectionLabel?: string
  suggestedEntityTypes?: string[]
}

type ArtifactKind = 'entity' | 'diagram' | 'document'
type FilterStage = 'kind' | 'scope' | 'entity-type'

const props = defineProps<Props>()
const emit = defineEmits<{
  insert: [markdownLink: string]
  select: [hit: ReferenceSearchHit]
  close: []
}>()

const svc = inject(modelServiceKey)!

const query = ref('')
const results = ref<ReferenceSearchHit[]>([])
const loading = ref(false)
const dropdownOpen = ref(false)
const currentStage = ref<FilterStage>('kind')
const selectedKind = ref<ArtifactKind | null>(null)
const selectedDomains = ref<string[]>([])
const selectedEntityTypes = ref<string[]>([])
const selectedDocTypes = ref<string[]>([])
const expandedDocs = ref<Record<string, boolean>>({})
const documentTypes = ref<DocumentType[]>([])
const writeHelp = ref<WriteHelp | null>(null)
let debounceTimer: ReturnType<typeof setTimeout> | null = null

const domainOptions = computed(() =>
  domainOptionsForDomains(Object.keys(writeHelp.value?.entity_types_by_domain ?? {})),
)
const diagramDomainOptions = computed(() => domainOptions.value.filter((option) => option.key !== 'common'))

const allKinds: ArtifactKind[] = ['entity', 'diagram', 'document']
const availableKinds = computed(() =>
  props.fixedKinds?.length ? props.fixedKinds : allKinds,
)
const kindIsLocked = computed(() => (props.fixedKinds?.length ?? 0) === 1)

const selectedDomainLabels = computed(() =>
  selectedDomains.value.map((domain) => getDomainLabel(domain)),
)

const suggestedEntityTypeSet = computed(() => rankedEntityTypeSet(props.suggestedEntityTypes))

const suggestedEntityTypeLabels = computed(() =>
  (props.suggestedEntityTypes ?? []).map(formatEntityTypeTerm),
)

const availableEntityTypes = computed(() => {
  const map = writeHelp.value?.entity_types_by_domain ?? {}
  const buckets = selectedDomains.value.length
    ? selectedDomains.value.flatMap((domain) => map[domain] ?? [])
    : Object.values(map).flat()
  const unique = [...new Set(buckets)].sort()
  const suggested = suggestedEntityTypeSet.value
  if (suggested.size === 0) return unique
  return [...unique.filter((t) => suggested.has(t)), ...unique.filter((t) => !suggested.has(t))]
})

const selectedDocTypeLabels = computed(() =>
  selectedDocTypes.value.map((docType) =>
    documentTypes.value.find((type) => type.doc_type === docType)?.name ?? docType,
  ),
)

const stageTitle = computed(() => {
  if (currentStage.value === 'kind') return '1. Choose Artifact Kind'
  if (currentStage.value === 'scope' && selectedKind.value === 'document') return '2. Filter Document Types'
  if (currentStage.value === 'scope') return '2. Filter Domains'
  return '3. Filter Entity Types'
})

const insertLink = (hit: ReferenceSearchHit, section?: string) => {
  emit('insert', buildReferenceMarkdown({
    currentPath: props.currentPath,
    targetPath: hit.path,
    title: hit.name,
    section,
  }))
  emit('select', hit)
  emit('close')
}

const toggleValue = (items: string[], value: string) =>
  items.includes(value) ? items.filter((item) => item !== value) : [...items, value]

const selectKind = (kind: ArtifactKind) => {
  selectedKind.value = kind
  selectedDomains.value = []
  selectedEntityTypes.value = []
  selectedDocTypes.value = []
  currentStage.value = kind === 'entity' || kind === 'diagram' || kind === 'document' ? 'scope' : 'kind'
}

const goBack = () => {
  if (currentStage.value === 'entity-type') {
    currentStage.value = 'scope'
    return
  }
  if (currentStage.value === 'scope' && !kindIsLocked.value) {
    currentStage.value = 'kind'
    selectedKind.value = null
    selectedDomains.value = []
    selectedEntityTypes.value = []
    selectedDocTypes.value = []
  }
}

const goForward = () => {
  if (selectedKind.value === 'entity' && currentStage.value === 'scope') {
    currentStage.value = 'entity-type'
  }
}

const runSearch = () => {
  if (!dropdownOpen.value || !selectedKind.value) {
    results.value = []
    return
  }
  loading.value = true
  void Effect.runPromise(svc.searchReferenceArtifacts({
    q: query.value.trim(),
    kind: selectedKind.value,
    domains: selectedKind.value === 'document' ? undefined : selectedDomains.value,
    entity_types: selectedKind.value === 'entity' ? selectedEntityTypes.value : undefined,
    doc_types: selectedKind.value === 'document' ? selectedDocTypes.value : undefined,
    limit: 30,
  })).then((result) => {
    results.value = [...result.hits]
    loading.value = false
  }).catch((error: unknown) => {
    console.error('Reference artifact search failed', readErrorMessage(error))
    results.value = []
    loading.value = false
  })
}

const scheduleSearch = () => {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(runSearch, 220)
}

watch(query, scheduleSearch)
watch([selectedKind, selectedDomains, selectedEntityTypes, selectedDocTypes], scheduleSearch, { deep: true })

onMounted(() => {
  if (props.fixedKinds?.length === 1) {
    selectKind(props.fixedKinds[0])
  }
  void Effect.runPromise(svc.listDocumentTypes())
    .then((types) => { documentTypes.value = types })
    .catch((error: unknown) => {
      console.error('Failed to load document types', readErrorMessage(error))
    })
  void Effect.runPromise(svc.getWriteHelp())
    .then((data) => { writeHelp.value = data })
    .catch((error: unknown) => {
      console.error('Failed to load write help', readErrorMessage(error))
    })
})
</script>

<template>
  <div class="reference-picker">
    <div class="reference-picker__header">
      <div>
        <h3>Insert Reference</h3>
        <p>Select an artifact, narrow it with staged filters, and insert a link at the cursor.</p>
      </div>
      <button
        class="reference-picker__close"
        type="button"
        @click="emit('close')"
      >
        ×
      </button>
    </div>

    <div
      v-if="sectionLabel"
      class="reference-picker__section-hint"
    >
      Inserting into section: <strong>{{ sectionLabel }}</strong>
      <span v-if="suggestedEntityTypeLabels.length">
        — suggested links: {{ suggestedEntityTypeLabels.join(', ') }}
      </span>
    </div>

    <div class="reference-picker__search">
      <input
        v-model="query"
        class="reference-picker__input"
        type="text"
        placeholder="Search by title, name, or artifact ID..."
        @focus="dropdownOpen = true"
        @click="dropdownOpen = true"
      >
    </div>

    <div
      v-if="dropdownOpen"
      class="reference-picker__dropdown"
    >
      <section class="reference-picker__filters">
        <div class="reference-picker__filters-header">
          <div class="reference-picker__stage-title">
            {{ stageTitle }}
          </div>
          <div class="reference-picker__nav">
            <button
              class="nav-btn"
              type="button"
              :disabled="currentStage === 'kind' || (kindIsLocked && currentStage === 'scope')"
              @click="goBack"
            >
              Back
            </button>
            <button
              v-if="selectedKind === 'entity' && currentStage === 'scope'"
              class="nav-btn nav-btn--primary"
              type="button"
              @click="goForward"
            >
              Entity Types
            </button>
          </div>
        </div>

        <div
          v-if="currentStage === 'kind'"
          class="reference-picker__chips"
        >
          <button
            v-for="kind in availableKinds"
            :key="kind"
            class="chip"
            :class="{ 'chip--active': selectedKind === kind }"
            type="button"
            @click="selectKind(kind)"
          >
            {{ kind }}
          </button>
        </div>

        <div
          v-else-if="currentStage === 'scope' && selectedKind === 'document'"
          class="reference-picker__chips"
        >
          <button
            v-for="docType in documentTypes"
            :key="docType.doc_type"
            class="chip"
            :class="{ 'chip--active': selectedDocTypes.includes(docType.doc_type) }"
            type="button"
            @click="selectedDocTypes = toggleValue(selectedDocTypes, docType.doc_type)"
          >
            {{ docType.name }}
          </button>
        </div>

        <div
          v-else-if="currentStage === 'scope'"
          class="reference-picker__chips"
        >
          <button
            v-for="domain in (selectedKind === 'diagram' ? diagramDomainOptions : domainOptions)"
            :key="domain.key"
            class="chip"
            :class="{ 'chip--active': selectedDomains.includes(domain.key) }"
            type="button"
            @click="selectedDomains = toggleValue(selectedDomains, domain.key)"
          >
            {{ domain.label }}
          </button>
        </div>

        <div
          v-else
          class="reference-picker__chips"
        >
          <button
            v-for="entityType in availableEntityTypes"
            :key="entityType"
            class="chip chip--small"
            :class="{
              'chip--active': selectedEntityTypes.includes(entityType),
              'chip--suggested': suggestedEntityTypeSet.has(entityType),
            }"
            type="button"
            @click="selectedEntityTypes = toggleValue(selectedEntityTypes, entityType)"
          >
            {{ entityType }}
          </button>
        </div>

        <div class="reference-picker__summary">
          <span v-if="selectedKind">Kind: <strong>{{ selectedKind }}</strong></span>
          <span v-if="selectedDomainLabels.length">Domains: <strong>{{ selectedDomainLabels.join(', ') }}</strong></span>
          <span v-if="selectedDocTypeLabels.length">Doc Types: <strong>{{ selectedDocTypeLabels.join(', ') }}</strong></span>
          <span v-if="selectedEntityTypes.length">Entity Types: <strong>{{ selectedEntityTypes.join(', ') }}</strong></span>
        </div>
      </section>

      <section class="reference-picker__results">
        <div
          v-if="!selectedKind"
          class="reference-picker__state"
        >
          Choose `entity`, `diagram`, or `document` first.
        </div>
        <div
          v-else-if="loading"
          class="reference-picker__state"
        >
          Searching…
        </div>
        <div
          v-else-if="!results.length"
          class="reference-picker__state"
        >
          No matches for the current filters.
        </div>

        <div
          v-else
          class="reference-picker__result-list"
        >
          <div
            v-for="hit in results"
            :key="hit.artifact_id"
            class="result-card"
          >
            <div class="result-card__row">
              <button
                class="result-card__main"
                type="button"
                @click="insertLink(hit)"
              >
                <span class="result-card__title">{{ hit.name }}</span>
                <span class="result-card__meta">
                  <span class="badge">{{ hit.record_type }}</span>
                  <span
                    v-if="hit.domain"
                    class="badge badge--muted"
                  >{{ hit.domain }}</span>
                  <span
                    v-if="hit.doc_type"
                    class="badge badge--muted"
                  >{{ hit.doc_type }}</span>
                  <span
                    v-if="hit.artifact_type"
                    class="badge badge--muted"
                  >{{ hit.artifact_type }}</span>
                  <span
                    v-if="hit.diagram_type"
                    class="badge badge--muted"
                  >{{ hit.diagram_type }}</span>
                </span>
              </button>
              <button
                v-if="hit.record_type === 'document' && hit.sections?.length"
                class="result-card__toggle"
                type="button"
                @click="expandedDocs = { ...expandedDocs, [hit.artifact_id]: !expandedDocs[hit.artifact_id] }"
              >
                {{ expandedDocs[hit.artifact_id] ? '▾' : '▸' }}
              </button>
            </div>

            <div class="result-card__path">
              {{ hit.path }}
            </div>

            <div
              v-if="hit.record_type === 'document' && expandedDocs[hit.artifact_id]"
              class="result-card__sections"
            >
              <button
                v-for="section in hit.sections ?? []"
                :key="section"
                class="section-chip"
                type="button"
                @click="insertLink(hit, section)"
              >
                # {{ section }}
              </button>
            </div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.reference-picker {
  width: min(820px, calc(100vw - 32px));
  background: white;
  border: 1px solid #dbe3ee;
  border-radius: 16px;
  box-shadow: 0 20px 50px rgba(15, 23, 42, 0.22);
  padding: 18px;
}

.reference-picker__header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.reference-picker__header h3 {
  font-size: 16px;
  font-weight: 700;
  color: #0f172a;
  margin-bottom: 4px;
}

.reference-picker__header p {
  font-size: 12px;
  color: #64748b;
}

.reference-picker__close {
  border: 0;
  background: transparent;
  color: #64748b;
  cursor: pointer;
  font-size: 22px;
  line-height: 1;
}

.reference-picker__section-hint {
  background: #eff6ff;
  border: 1px solid #bfdbfe;
  color: #1e40af;
  border-radius: 8px;
  padding: 7px 11px;
  font-size: 12px;
  margin-bottom: 10px;
}

.reference-picker__input {
  width: 100%;
  padding: 11px 13px;
  border: 1px solid #cbd5e1;
  border-radius: 10px;
  font-size: 14px;
}

.reference-picker__input:focus {
  outline: none;
  border-color: #2563eb;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
}

.reference-picker__dropdown {
  margin-top: 12px;
  display: grid;
  grid-template-rows: auto minmax(260px, 42vh);
  gap: 12px;
}

.reference-picker__filters,
.reference-picker__results {
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  background: #f8fafc;
}

.reference-picker__filters {
  padding: 14px;
}

.reference-picker__filters-header {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
  margin-bottom: 12px;
}

.reference-picker__stage-title {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #475569;
}

.reference-picker__nav {
  display: flex;
  gap: 8px;
}

.nav-btn {
  border: 1px solid #cbd5e1;
  background: white;
  color: #334155;
  border-radius: 8px;
  padding: 7px 10px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.nav-btn:disabled {
  opacity: 0.45;
  cursor: default;
}

.nav-btn--primary {
  background: #dbeafe;
  border-color: #bfdbfe;
  color: #1d4ed8;
}

.reference-picker__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.chip {
  border: 1px solid #cbd5e1;
  background: white;
  border-radius: 999px;
  padding: 7px 12px;
  font-size: 12px;
  color: #334155;
  cursor: pointer;
}

.chip--small {
  font-size: 11px;
}

.chip--active {
  background: #0f172a;
  border-color: #0f172a;
  color: white;
}

.chip--suggested:not(.chip--active) {
  border-color: #93c5fd;
  background: #eff6ff;
  color: #1e40af;
}

.reference-picker__summary {
  margin-top: 14px;
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  font-size: 12px;
  color: #64748b;
}

.reference-picker__results {
  padding: 12px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.reference-picker__state {
  color: #64748b;
  font-size: 13px;
  padding: 8px 4px;
}

.reference-picker__result-list {
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.result-card {
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  padding: 10px 12px;
}

.result-card__row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.result-card__main {
  flex: 1;
  border: 0;
  background: transparent;
  padding: 0;
  cursor: pointer;
  text-align: left;
}

.result-card__title {
  display: block;
  font-size: 13px;
  font-weight: 700;
  color: #0f172a;
  margin-bottom: 6px;
}

.result-card__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.badge {
  display: inline-flex;
  padding: 2px 8px;
  border-radius: 999px;
  background: #dbeafe;
  color: #1d4ed8;
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
}

.badge--muted {
  background: #f1f5f9;
  color: #475569;
}

.result-card__toggle {
  border: 0;
  background: transparent;
  color: #64748b;
  cursor: pointer;
  font-size: 16px;
}

.result-card__path {
  margin-top: 8px;
  font-size: 11px;
  color: #94a3b8;
  word-break: break-all;
}

.result-card__sections {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}

.section-chip {
  border: 1px solid #bfdbfe;
  background: #eff6ff;
  color: #1d4ed8;
  border-radius: 999px;
  padding: 5px 9px;
  font-size: 11px;
  cursor: pointer;
}

@media (max-width: 760px) {
  .reference-picker {
    width: min(100vw - 20px, 100%);
    padding: 14px;
  }

  .reference-picker__dropdown {
    grid-template-rows: auto minmax(300px, 44vh);
  }

  .reference-picker__filters-header {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
