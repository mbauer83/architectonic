<script setup lang="ts">
import { inject, ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Effect } from 'effect'
import { modelServiceKey } from '../keys'
import type {
  EntityDisplayInfo, EntityContextConnection, DiagramPreviewResult, WriteResult,
  DiagramTypeUiConfig, ViewpointSummary,
} from '../../domain'
import EntitySelectionList from '../components/EntitySelectionList.vue'
import EntityPickerInput from '../components/EntityPickerInput.vue'
import DiagramTypeSelect from '../components/DiagramTypeSelect.vue'
import DiagramTypeConfigPanel from '../components/DiagramTypeConfigPanel.vue'
import PreviewViewport from '../components/PreviewViewport.vue'
import ArchimateOccurrenceControls from '../components/ArchimateOccurrenceControls.vue'
import ViewpointSelect from '../components/ViewpointSelect.vue'
import { findViewpointBySlug } from '../components/ViewpointSelect.helpers'
import { isArchimateDiagramType } from '../lib/archimateOccurrences'
import { loadViewpointSummaries } from '../lib/viewpointSummary'

const svc = inject(modelServiceKey)!
const route = useRoute()
const router = useRouter()

const name = ref('')
const diagramType = ref((route.query.type as string | undefined) ?? 'archimate-business')
const uiConfig = ref<DiagramTypeUiConfig | null>(null)
const diagramEntities = ref<Record<string, unknown>>({})
const viewpoints = ref<ViewpointSummary[]>([])
const viewpointSlug = ref<string | null>(null)
let _lastSuggestedName = ''

const loadViewpoints = async () => {
  viewpoints.value = await loadViewpointSummaries(svc.listViewpointDefinitions())
}

const mergeDiagramEntities = (patch: Record<string, unknown>) => {
  diagramEntities.value = { ...diagramEntities.value, ...patch }
  // Auto-suggest name when scope entity is set for C4 diagrams
  const scopeName = typeof patch._scope_entity_name === 'string' ? patch._scope_entity_name : ''
  if (scopeName && uiConfig.value?.label) {
    const suggested = `${scopeName} — ${uiConfig.value.label}`
    if (!name.value || name.value === _lastSuggestedName) {
      name.value = suggested
      _lastSuggestedName = suggested
    }
  }
  preview.value = null
  previewClean.value = false
}

const setDiagramEntities = (next: Record<string, unknown>) => {
  diagramEntities.value = next
  preview.value = null
  previewClean.value = false
}

const loadUiConfig = async () => {
  uiConfig.value = await Effect.runPromise(svc.getDiagramTypeUiConfig(diagramType.value)).catch(() => null)
}

const selectDiagramType = () => {
  void loadUiConfig()
}

const includedEntities = ref<EntityDisplayInfo[]>([])
const highlightedEntityIds = ref<Set<string>>(new Set())
const expandedConnectionEntityIds = ref<Set<string>>(new Set())
const expandedRelatedEntityIds = ref<Set<string>>(new Set())
const includedEntityIds = computed(() => new Set(includedEntities.value.map((e) => e.artifact_id)))

const allModelConns = ref<Map<string, EntityContextConnection>>(new Map())
const includedConnIds = ref<Set<string>>(new Set())

const selectionRows = computed(() =>
  includedEntities.value.map((entity) => ({
    entity,
    newInclusion: highlightedEntityIds.value.has(entity.artifact_id),
    badgeText: highlightedEntityIds.value.has(entity.artifact_id) ? 'new' : undefined,
    actionKind: 'remove' as const,
    actionTitle: 'Remove entity from diagram',
  })),
)

const relatedEntitiesById = computed<Record<string, EntityDisplayInfo[]>>(() => {
  const related: Record<string, EntityDisplayInfo[]> = {}
  const seenByEntity = new Map<string, Set<string>>()
  for (const entity of includedEntities.value) related[entity.artifact_id] = []
  for (const conn of allModelConns.value.values()) {
    const endpoints: Array<[string, string]> = [
      [conn.source, conn.target],
      [conn.target, conn.source],
    ]
    for (const [ownerId, otherId] of endpoints) {
      if (!includedEntityIds.value.has(ownerId) || includedEntityIds.value.has(otherId)) continue
      const name = ownerId === conn.source ? (conn.target_name ?? otherId) : (conn.source_name ?? otherId)
      const artifactType = ownerId === conn.source ? conn.target_artifact_type : conn.source_artifact_type
      const domain = ownerId === conn.source ? conn.target_domain : conn.source_domain
      const scope = ownerId === conn.source ? conn.target_scope : conn.source_scope
      const seen = seenByEntity.get(ownerId) ?? new Set<string>()
      if (seen.has(otherId)) continue
      seen.add(otherId)
      seenByEntity.set(ownerId, seen)
      related[ownerId].push({
        artifact_id: otherId,
        name,
        artifact_type: artifactType,
        domain,
        subdomain: '',
        status: scope,
        display_alias: '',
        element_type: artifactType,
        element_label: name, diagram_internal: false,
      })
    }
  }
  for (const entityId of Object.keys(related)) {
    related[entityId].sort((a, b) => a.name.localeCompare(b.name))
  }
  return related
})

const refreshDiscovery = async () => {
  const discovery = await Effect.runPromise(
    svc.discoverDiagramEntities({
      includedEntityIds: includedEntities.value.map((e) => e.artifact_id),
      diagramType: diagramType.value,
      viewpoint: viewpointSlug.value ?? undefined,
      maxHops: 1,
      limit: 20,
    }),
  ).catch(() => null)
  if (!discovery) return
  allModelConns.value = new Map(discovery.candidate_connections.map((conn) => [conn.artifact_id, conn]))
}

const addEntity = async (entity: EntityDisplayInfo) => {
  if (includedEntityIds.value.has(entity.artifact_id)) return
  includedEntities.value.push(entity)
  highlightedEntityIds.value = new Set(highlightedEntityIds.value).add(entity.artifact_id)
  expandedRelatedEntityIds.value = new Set(expandedRelatedEntityIds.value)
  await refreshDiscovery()
  const nextConnIds = new Set(includedConnIds.value)
  for (const conn of allModelConns.value.values()) {
    const otherId = conn.source === entity.artifact_id ? conn.target : conn.source
    if ((conn.source === entity.artifact_id || conn.target === entity.artifact_id) && includedEntityIds.value.has(otherId)) {
      nextConnIds.add(conn.artifact_id)
    }
  }
  includedConnIds.value = nextConnIds
}

const removeEntity = (artifactId: string) => {
  includedEntities.value = includedEntities.value.filter((e) => e.artifact_id !== artifactId)
  const nextHighlighted = new Set(highlightedEntityIds.value)
  nextHighlighted.delete(artifactId)
  highlightedEntityIds.value = nextHighlighted
  const nextExpandedConns = new Set(expandedConnectionEntityIds.value)
  nextExpandedConns.delete(artifactId)
  expandedConnectionEntityIds.value = nextExpandedConns
  const nextExpandedRelated = new Set(expandedRelatedEntityIds.value)
  nextExpandedRelated.delete(artifactId)
  expandedRelatedEntityIds.value = nextExpandedRelated
  const nextConnIds = new Set(includedConnIds.value)
  for (const id of [...nextConnIds]) {
    const c = allModelConns.value.get(id)
    if (c && (c.source === artifactId || c.target === artifactId)) nextConnIds.delete(id)
  }
  includedConnIds.value = nextConnIds
  void refreshDiscovery()
}

const toggleConnections = (entityId: string) => {
  const next = new Set(expandedConnectionEntityIds.value)
  if (next.has(entityId)) next.delete(entityId)
  else next.add(entityId)
  expandedConnectionEntityIds.value = next
}

const toggleRelated = (entityId: string) => {
  const next = new Set(expandedRelatedEntityIds.value)
  if (next.has(entityId)) next.delete(entityId)
  else next.add(entityId)
  expandedRelatedEntityIds.value = next
}

const toggleConnection = (id: string) => {
  const next = new Set(includedConnIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  includedConnIds.value = next
}

watch(name, () => {
  preview.value = null
  previewClean.value = false
})

const preview = ref<DiagramPreviewResult | null>(null)
const previewBusy = ref(false)
const previewError = ref<string | null>(null)
const previewClean = ref(false)
const previewIssues = ref<string[]>([])
const showPuml = ref(false)

const excludedEntityIds = computed(() => {
  const raw = diagramEntities.value._excluded_entity_ids
  return new Set<string>(Array.isArray(raw) ? (raw as unknown[]).map(String) : [])
})

const toggleExclusion = (entityId: string) => {
  const current = [...excludedEntityIds.value]
  const updated = current.includes(entityId)
    ? current.filter((id) => id !== entityId)
    : [...current, entityId]
  diagramEntities.value = { ...diagramEntities.value, _excluded_entity_ids: updated }
  previewClean.value = false
}

const mergedEntityIds = () => {
  const base = includedEntities.value.map((e) => e.artifact_id)
  const mapped = (diagramEntities.value.entity_ids_mapped as string[] | undefined) ?? []
  return [...new Set([...base, ...mapped])]
}

const doPreview = () => {
  previewBusy.value = true
  previewError.value = null
  previewIssues.value = []
  void Effect.runPromise(
    svc.previewDiagram({
      diagram_type: diagramType.value,
      name: name.value,
      entity_ids: mergedEntityIds(),
      connection_ids: [...includedConnIds.value],
      diagram_entities: diagramEntities.value,
    }),
  )
    .then((r) => {
      preview.value = r
      previewClean.value = true
      previewIssues.value = []
      previewBusy.value = false
    })
    .catch((e) => { previewError.value = String(e); previewBusy.value = false })
}

const createBusy = ref(false)
const createError = ref<string | null>(null)

const writeFailureMessage = (result: WriteResult): string => {
  const verification = result.verification as { issues?: Array<{ message?: string }> } | null
  const issues = verification?.issues?.map((issue) => issue.message).filter((m): m is string => Boolean(m)) ?? []
  if (issues.length) return issues.join(' | ')
  return result.content ?? 'Verification failed — check warnings'
}

const doCreate = () => {
  createBusy.value = true
  createError.value = null
  const selectedViewpoint = findViewpointBySlug(viewpoints.value, viewpointSlug.value)
  void Effect.runPromise(
    svc.createDiagram({
      diagram_type: diagramType.value,
      name: name.value,
      entity_ids: mergedEntityIds(),
      connection_ids: [...includedConnIds.value],
      diagram_entities: diagramEntities.value,
      viewpoint: selectedViewpoint ? { slug: selectedViewpoint.slug, version: selectedViewpoint.version } : null,
      dry_run: false,
    }),
  )
    .then((r) => {
      createBusy.value = false
      if (r.wrote) void router.push({ path: '/diagram', query: { id: r.artifact_id } })
      else createError.value = writeFailureMessage(r)
    })
    .catch((e) => { createBusy.value = false; createError.value = String(e) })
}


onMounted(() => { void refreshDiscovery(); void loadViewpoints() })
watch(viewpointSlug, () => { void refreshDiscovery() })
watch(diagramType, () => {
  diagramEntities.value = {}
  preview.value = null
  previewClean.value = false
  void loadUiConfig()
  void refreshDiscovery()
})
</script>

<template>
  <div class="layout">
    <div class="page-header">
      <button
        class="back-link"
        @click="router.back()"
      >
        ← Back
      </button>
      <h1 class="page-title">
        Create Diagram
      </h1>
    </div>

    <div class="columns">
      <section class="card form-col">
        <div class="form-row">
          <label class="lbl">Name <span class="req">*</span></label>
          <input
            v-model="name"
            class="inp"
            placeholder="Diagram name"
          >
        </div>

        <div class="form-row">
          <label class="lbl">Diagram Type</label>
          <DiagramTypeSelect
            v-model="diagramType"
            @select="selectDiagramType"
          />
        </div>

        <div class="form-row">
          <label class="lbl">Viewpoint</label>
          <ViewpointSelect
            v-model="viewpointSlug"
            :viewpoints="viewpoints"
          />
        </div>

        <DiagramTypeConfigPanel
          :ui-config="uiConfig"
          :diagram-entities="diagramEntities"
          :entities="includedEntities"
          diagram-id=""
          @diagram-entities-change="mergeDiagramEntities"
        />

        <div
          v-if="isArchimateDiagramType(diagramType) && includedEntities.length"
          class="form-row"
        >
          <ArchimateOccurrenceControls
            :diagram-entities="diagramEntities"
            :entities="includedEntities"
            @change="setDiagramEntities"
          />
        </div>

        <div
          v-if="uiConfig?.entity_search_filter !== false"
          class="form-row"
        >
          <label class="lbl">Add Entities</label>
          <EntityPickerInput
            :excluded-ids="includedEntityIds"
            :diagram-type="diagramType"
            :viewpoint="viewpointSlug ?? undefined"
            @select="addEntity"
          />
        </div>

        <div
          v-if="uiConfig?.entity_search_filter !== false && includedEntities.length"
          class="form-row"
        >
          <label class="lbl">Included Entities ({{ includedEntities.length }})</label>
          <EntitySelectionList
            :rows="selectionRows"
            :candidate-connections="[...allModelConns.values()]"
            :included-entity-ids="[...includedEntityIds]"
            :included-connection-ids="[...includedConnIds]"
            :related-entities-by-id="relatedEntitiesById"
            :expanded-connection-entity-ids="[...expandedConnectionEntityIds]"
            :expanded-related-entity-ids="[...expandedRelatedEntityIds]"
            @toggle-connections="toggleConnections"
            @toggle-related="toggleRelated"
            @toggle-connection="toggleConnection"
            @add-related-entity="addEntity"
            @entity-action="removeEntity"
          />
        </div>

        <div
          v-if="createError"
          class="state-err"
        >
          {{ createError }}
        </div>

        <div class="actions">
          <button
            class="btn-preview"
            :disabled="previewBusy || !name.trim() || (uiConfig?.entity_search_filter !== false && !includedEntities.length)"
            @click="doPreview"
          >
            {{ previewBusy ? 'Rendering…' : 'Preview' }}
          </button>
          <button
            class="btn-create"
            :disabled="createBusy || !previewClean"
            :title="!previewClean ? 'Run preview first to enable create' : ''"
            @click="doCreate"
          >
            {{ createBusy ? 'Creating…' : 'Create Diagram' }}
          </button>
        </div>
      </section>

      <section class="card preview-col">
        <div
          v-if="!preview && !previewBusy && !previewError"
          class="preview-hint"
        >
          {{ uiConfig?.entity_search_filter !== false ? 'Select entities and connections, then click' : 'Configure the diagram, then click' }}
          <strong>Preview</strong>.
        </div>
        <div
          v-if="previewBusy"
          class="state-msg"
        >
          Rendering…
        </div>
        <div
          v-if="previewError"
          class="state-err"
        >
          {{ previewError }}
        </div>

        <template v-if="preview">
          <div
            v-if="!previewClean"
            class="state-err"
          >
            <strong>Verification issues found:</strong>
            <ul style="margin-top: 4px; font-size: 12px; margin-bottom: 0; padding-left: 18px;">
              <li
                v-for="issue in previewIssues"
                :key="issue"
              >
                {{ issue }}
              </li>
            </ul>
          </div>
          <div
            v-else
            class="state-msg"
          >
            Verification passed.
          </div>
          <PreviewViewport
            v-if="preview.image"
            :reset-signal="preview"
          >
            <img
              :src="preview.image"
              class="preview-img"
              alt="Diagram preview"
              draggable="false"
            >
          </PreviewViewport>
          <div
            v-else
            class="state-msg"
          >
            No image could be rendered.
            <ul
              v-if="preview.warnings.length"
              class="render-warnings"
            >
              <li
                v-for="w in preview.warnings"
                :key="w"
              >
                {{ w }}
              </li>
            </ul>
          </div>
          <!-- Derived entity checklist (model-backed C4) -->
          <template v-if="preview.derived_entities !== null && preview.derived_entities !== undefined">
            <div
              v-if="preview.derived_entities.length === 0"
              class="derived-empty"
            >
              No external connections found — consider a C4 Container diagram instead.
            </div>
            <div
              v-else
              class="derived-list"
            >
              <div class="derived-hdr">
                {{ preview.derived_entities.length }} entities auto-derived
                <span
                  v-if="excludedEntityIds.size"
                  class="derived-excluded-badge"
                >{{ excludedEntityIds.size }} excluded</span>
                — uncheck to exclude, then re-preview:
              </div>
              <label
                v-for="item in preview.derived_entities"
                :key="item.id"
                class="derived-item"
              >
                <input
                  type="checkbox"
                  :checked="!excludedEntityIds.has(item.id)"
                  @change="toggleExclusion(item.id)"
                >
                <span class="derived-name">{{ item.name }}</span>
                <span class="derived-type">{{ item.item_type }}</span>
              </label>
            </div>
          </template>

          <button
            class="toggle-src"
            @click="showPuml = !showPuml"
          >
            {{ showPuml ? 'Hide' : 'Show' }} PUML source
          </button>
          <pre
            v-if="showPuml"
            class="puml-src"
          >{{ preview.puml }}</pre>
        </template>
      </section>
    </div>
  </div>
</template>

<style scoped>
.layout { max-width: 1200px; margin: 0 auto; }
.page-header { display: flex; align-items: center; gap: 16px; margin-bottom: 24px; }
.back-link { font-size: 13px; color: #6b7280; background: none; border: none; cursor: pointer; padding: 0; }
.back-link:hover { color: #374151; }
.page-title { font-size: 20px; font-weight: 600; margin: 0; }

.columns { display: grid; grid-template-columns: 480px 1fr; gap: 20px; align-items: start; }
@media (max-width: 860px) { .columns { grid-template-columns: 1fr; } }

.card { background: white; border-radius: 8px; border: 1px solid #e5e7eb; padding: 20px; }
.form-row { margin-bottom: 14px; }
.lbl { display: block; font-size: 11px; font-weight: 700; color: #374151; margin-bottom: 4px; text-transform: uppercase; letter-spacing: .05em; }
.req { color: #dc2626; }
.inp { width: 100%; padding: 7px 10px; border-radius: 6px; border: 1px solid #d1d5db; font-size: 13px; outline: none; box-sizing: border-box; background: white; }
.inp:focus { border-color: #2563eb; }

.actions { display: flex; gap: 8px; justify-content: flex-end; padding-top: 8px; }
.btn-preview { padding: 7px 16px; background: #f3f4f6; color: #1d4ed8; border: 1px solid #bfdbfe; border-radius: 6px; font-size: 13px; cursor: pointer; font-weight: 500; }
.btn-preview:hover:not(:disabled) { background: #eff6ff; }
.btn-create { padding: 7px 16px; background: #16a34a; color: white; border: none; border-radius: 6px; font-size: 13px; font-weight: 500; cursor: pointer; }
.btn-create:hover:not(:disabled) { background: #15803d; }
.btn-preview:disabled, .btn-create:disabled { opacity: .5; cursor: not-allowed; }
.state-msg { font-size: 13px; color: #6b7280; }
.state-err { font-size: 13px; color: #dc2626; margin-top: 6px; }
.warn { font-size: 12px; color: #b45309; margin-bottom: 4px; }
.preview-hint { font-size: 13px; color: #9ca3af; }
.preview-img { max-width: none; display: block; }
.toggle-src { margin-top: 10px; font-size: 12px; color: #2563eb; background: none; border: none; cursor: pointer; padding: 0; }
.toggle-src:hover { text-decoration: underline; }
.puml-src { font-size: 11px; font-family: monospace; white-space: pre-wrap; margin-top: 8px; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px; padding: 10px; max-height: 400px; overflow-y: auto; }
.render-warnings { margin: 6px 0 0 0; padding-left: 18px; font-size: 12px; color: #b45309; }
.derived-empty { margin-top: 10px; font-size: 12px; color: #b45309; padding: 8px 10px; background: #fffbeb; border: 1px solid #fde68a; border-radius: 6px; }
.derived-list { margin-top: 10px; border: 1px solid #e5e7eb; border-radius: 6px; padding: 8px 10px; background: #f9fafb; }
.derived-hdr { font-size: 11px; font-weight: 600; color: #374151; margin-bottom: 6px; }
.derived-excluded-badge { background: #fee2e2; color: #b91c1c; border-radius: 3px; padding: 1px 5px; font-size: 10px; margin-left: 4px; }
.derived-item { display: flex; align-items: center; gap: 6px; padding: 3px 0; cursor: pointer; font-size: 12px; }
.derived-item input[type=checkbox] { cursor: pointer; }
.derived-name { color: #1e293b; font-weight: 500; }
.derived-type { color: #9ca3af; font-size: 11px; }
</style>
