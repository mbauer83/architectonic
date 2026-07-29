<script setup lang="ts">
import { ref, computed, inject } from 'vue'
import { useRouter, RouterLink } from 'vue-router'
import { Effect, Exit } from 'effect'
import { modelServiceKey } from '../keys'
import { useMatrixEditor } from '../composables/useMatrixEditor'
import MatrixEntityList from '../components/MatrixEntityList.vue'
import MatrixConnTypeList from '../components/MatrixConnTypeList.vue'
import EntityPickerInput from '../components/EntityPickerInput.vue'
import type { EntityDisplayInfo } from '../../domain'
import { renderMatrixMarkdown } from '../lib/matrixMarkdown'

const svc = inject(modelServiceKey)!
const router = useRouter()

const name = ref('')
const combined = ref(false)
const previewHtml = ref('')
const busy = ref(false)
const error = ref('')

const asymmetric = ref(false)
const toEntityOrder = ref<EntityDisplayInfo[]>([])
const toEntityIds = computed(() => toEntityOrder.value.map(e => e.artifact_id))
const toIncludedIds = computed(() => new Set(toEntityIds.value))

const {
  entityOrder, connTypeConfigs, relatedEntitiesById, toRelatedEntitiesById,
  connCountsByType, addEntity, removeEntity, reorderEntities,
  toggleConnType, reorderConnTypes,
} = useMatrixEditor({ toEntityIds: () => asymmetric.value ? toEntityIds.value : [] })

const entityIds = computed(() => entityOrder.value.map(e => e.artifact_id))
const includedIds = computed(() => new Set(entityIds.value))

const addToEntity = (entity: EntityDisplayInfo) => {
  if (!toIncludedIds.value.has(entity.artifact_id))
    toEntityOrder.value = [...toEntityOrder.value, entity]
}
const removeToEntity = (id: string) => {
  toEntityOrder.value = toEntityOrder.value.filter(e => e.artifact_id !== id)
}
const reorderToEntities = (fromIdx: number, toIdx: number) => {
  const arr = [...toEntityOrder.value]
  const [moved] = arr.splice(fromIdx, 1)
  arr.splice(toIdx, 0, moved)
  toEntityOrder.value = arr
}

const setMode = (twoSets: boolean) => {
  if (twoSets === asymmetric.value) return
  if (twoSets) {
    toEntityOrder.value = [...entityOrder.value]
  } else {
    const seen = new Set(entityOrder.value.map(e => e.artifact_id))
    const merged = [...entityOrder.value]
    for (const e of toEntityOrder.value) {
      if (!seen.has(e.artifact_id)) { merged.push(e); seen.add(e.artifact_id) }
    }
    entityOrder.value = merged
    toEntityOrder.value = []
  }
  asymmetric.value = twoSets
}

const doPreview = async () => {
  if (!entityIds.value.length) { error.value = 'Add at least one entity.'; return }
  busy.value = true; error.value = ''
  const exit = await Effect.runPromiseExit(svc.previewMatrix({
    entity_ids: entityIds.value,
    conn_type_configs: connTypeConfigs.value,
    combined: combined.value,
    from_entity_ids: asymmetric.value ? entityIds.value : undefined,
    to_entity_ids: asymmetric.value ? toEntityIds.value : undefined,
  }))
  busy.value = false
  if (Exit.isSuccess(exit)) {
    previewHtml.value = renderMatrixMarkdown(exit.value.markdown)
    return
  }
  error.value = String(exit.cause)
}

const doCreate = async () => {
  if (!name.value.trim()) { error.value = 'Name is required.'; return }
  if (!entityIds.value.length) { error.value = 'Add at least one entity.'; return }
  busy.value = true; error.value = ''
  const exit = await Effect.runPromiseExit(svc.createMatrixDiagram({
    name: name.value.trim(),
    entity_ids: entityIds.value, conn_type_configs: connTypeConfigs.value,
    combined: combined.value, dry_run: false,
    from_entity_ids: asymmetric.value ? entityIds.value : undefined,
    to_entity_ids: asymmetric.value ? toEntityIds.value : undefined,
  }))
  busy.value = false
  Exit.match(exit, {
    onSuccess: (r) => { if (r.wrote) void router.push({ path: '/diagram', query: { id: r.artifact_id } }) },
    onFailure: (e) => { error.value = String(e) },
  })
}
</script>

<template>
  <div class="page">
    <div class="page-hdr">
      <RouterLink
        to="/diagrams"
        class="back"
      >
        ← Diagrams
      </RouterLink>
      <h1 class="pg-title">
        New Matrix Diagram
      </h1>
    </div>

    <div class="meta-card card">
      <div class="field">
        <label class="lbl">Name</label>
        <input
          v-model="name"
          class="inp"
          placeholder="Diagram name"
        >
      </div>
      <label class="combined-row">
        <input
          v-model="combined"
          type="checkbox"
        > Combine connection-types
      </label>
    </div>

    <div class="two-col">
      <div class="card panel">
        <div class="panel-hdr">
          <span class="panel-title">Entities</span>
        </div>
        <div class="mode-toggle">
          <button
            class="mode-btn"
            :class="{ 'mode-btn--active': !asymmetric }"
            type="button"
            @click="setMode(false)"
          >
            Single set
          </button>
          <button
            class="mode-btn"
            :class="{ 'mode-btn--active': asymmetric }"
            type="button"
            @click="setMode(true)"
          >
            From &amp; To
          </button>
        </div>
        <template v-if="asymmetric">
          <div class="subsection-lbl">
            From (rows)
          </div>
          <div class="picker-wrap">
            <EntityPickerInput
              :excluded-ids="includedIds"
              @select="addEntity"
            />
          </div>
          <MatrixEntityList
            :entities="entityOrder"
            :related-entities-by-id="relatedEntitiesById"
            @remove="removeEntity"
            @reorder="reorderEntities"
            @add-related="addEntity"
          />
          <div class="subsection-lbl">
            To (columns)
          </div>
          <div class="picker-wrap">
            <EntityPickerInput
              :excluded-ids="toIncludedIds"
              @select="addToEntity"
            />
          </div>
          <MatrixEntityList
            :entities="toEntityOrder"
            :related-entities-by-id="toRelatedEntitiesById"
            @remove="removeToEntity"
            @reorder="reorderToEntities"
            @add-related="addToEntity"
          />
        </template>
        <template v-else>
          <div class="picker-wrap">
            <EntityPickerInput
              :excluded-ids="includedIds"
              @select="addEntity"
            />
          </div>
          <MatrixEntityList
            :entities="entityOrder"
            :related-entities-by-id="relatedEntitiesById"
            @remove="removeEntity"
            @reorder="reorderEntities"
            @add-related="addEntity"
          />
        </template>
      </div>
      <div class="card panel">
        <div class="panel-hdr">
          <span class="panel-title">Connection Types</span>
        </div>
        <MatrixConnTypeList
          :conn-type-configs="connTypeConfigs"
          :conn-counts-by-type="connCountsByType"
          @toggle="toggleConnType"
          @reorder="reorderConnTypes"
        />
      </div>
    </div>

    <div
      v-if="error"
      class="err-msg"
    >
      {{ error }}
    </div>

    <div class="actions">
      <button
        class="btn-secondary"
        :disabled="busy"
        @click="doPreview"
      >
        Preview
      </button>
      <button
        class="btn-primary"
        :disabled="busy"
        @click="doCreate"
      >
        Create Diagram
      </button>
    </div>

    <div
      v-if="previewHtml"
      class="matrix-preview card"
      v-html="previewHtml"
    />
  </div>
</template>

<style scoped>
.page { max-width: 1100px; margin: 0 auto; padding: 24px 16px; }
.page-hdr { display: flex; align-items: center; gap: 16px; margin-bottom: 20px; }
.back { font-size: 13px; color: #6b7280; text-decoration: none; }
.back:hover { color: #374151; }
.pg-title { font-size: 20px; font-weight: 600; margin: 0; }
.card { background: white; border-radius: 8px; border: 1px solid #e5e7eb; }
.meta-card { padding: 16px; margin-bottom: 16px; display: flex; flex-direction: column; gap: 12px; }
.field { display: flex; flex-direction: column; gap: 4px; }
.lbl { font-size: 12px; font-weight: 600; color: #374151; }
.inp { border: 1px solid #d1d5db; border-radius: 6px; padding: 7px 10px; font-size: 13px; }
.inp:focus { outline: none; border-color: #2563eb; }
.combined-row { display: flex; align-items: center; gap: 8px; font-size: 13px; color: #374151; cursor: pointer; }
.mode-toggle { display: inline-flex; border: 1px solid #d1d5db; border-radius: 6px; overflow: hidden; margin-bottom: 10px; }
.mode-btn { padding: 5px 14px; font-size: 12px; font-weight: 500; color: #374151; background: white; border: none; cursor: pointer; }
.mode-btn + .mode-btn { border-left: 1px solid #d1d5db; }
.mode-btn--active { background: #0f172a; color: white; }
.mode-btn:not(.mode-btn--active):hover { background: #f9fafb; }
.subsection-lbl { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: #6b7280; margin: 8px 0 4px; }
.two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }
.panel { padding: 12px; min-width: 0; }
.panel-hdr { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.panel-title { font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: #6b7280; }
.picker-wrap { margin-bottom: 10px; position: relative; }
.err-msg { color: #dc2626; font-size: 13px; margin-bottom: 10px; }
.actions { display: flex; gap: 10px; margin-bottom: 20px; }
.btn-primary { padding: 8px 20px; background: #2563eb; color: white; border: none; border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer; }
.btn-primary:hover:not(:disabled) { background: #1d4ed8; }
.btn-primary:disabled { opacity: .5; cursor: not-allowed; }
.btn-secondary { padding: 8px 20px; background: white; color: #374151; border: 1px solid #d1d5db; border-radius: 6px; font-size: 13px; font-weight: 500; cursor: pointer; }
.btn-secondary:hover:not(:disabled) { background: #f9fafb; }
.btn-secondary:disabled { opacity: .5; cursor: not-allowed; }
.matrix-preview { padding: 16px; overflow: auto; max-height: clamp(300px, 60vh, 700px); }
.matrix-preview :deep(table) { border-collapse: collapse; margin-bottom: 20px; }
.matrix-preview :deep(th) {
  border: 1px solid #e2e8f0; padding: 6px 8px; font-size: 11px; font-weight: 600;
  min-width: 5rem; max-width: 9rem;
  text-align: center; vertical-align: bottom; white-space: normal; word-break: break-word;
}
.matrix-preview :deep(th:first-child) {
  position: sticky; left: 0; z-index: 2; background: white;
  text-align: left; min-width: 10rem; max-width: 16rem; border-right: 2px solid #d1d5db;
}
.matrix-preview :deep(td) { border: 1px solid #e2e8f0; padding: 4px 8px; font-size: 12px; }
.matrix-preview :deep(td:first-child) {
  position: sticky; left: 0; z-index: 1; background: white;
  font-size: 11px; font-weight: 500; min-width: 10rem; max-width: 16rem;
  word-break: break-word; border-right: 2px solid #d1d5db;
}
.matrix-preview :deep(td:not(:first-child)) { text-align: center; }
.matrix-preview :deep(h2) { font-size: 13px; font-weight: 700; margin: 16px 0 6px; color: #374151; }
</style>
