<script setup lang="ts">
import { computed, inject, onMounted, onUnmounted } from 'vue'
import { useRoute } from 'vue-router'
import { modelServiceKey } from '../keys'
import EntitySelectionList from '../components/EntitySelectionList.vue'
import PromotionArtifactGroup from '../components/PromotionArtifactGroup.vue'
import PromotionPlanSummary from '../components/PromotionPlanSummary.vue'
import { usePromotionWorkflow } from '../composables/usePromotionWorkflow'
import { artifactKindLabel } from '../composables/promotionShared'

const svc = inject(modelServiceKey)!
const route = useRoute()

const workflow = usePromotionWorkflow(svc, computed(() => route.query as Record<string, unknown>))

onMounted(() => {
  void workflow.initializeFromRoute()
})
onUnmounted(() => {
  workflow.cleanup()
})
</script>

<template>
  <div class="promote-view">
    <div class="page-header">
      <h1 class="page-title">
        Promote to Enterprise Repository
      </h1>
      <p class="page-sub">
        Build an explicit promotion set of entities, documents, and diagrams, review conflicts, then execute.
      </p>
    </div>

    <div class="steps">
      <div
        class="step"
        :class="{ active: workflow.step.value === 'pick', done: workflow.step.value !== 'pick' }"
      >
        1. Select root
      </div>
      <div class="step-arrow">
        ›
      </div>
      <div
        class="step"
        :class="{ active: workflow.step.value === 'review', done: workflow.step.value === 'execute' || workflow.step.value === 'done' }"
      >
        2. Curate set
      </div>
      <div class="step-arrow">
        ›
      </div>
      <div
        class="step"
        :class="{ active: workflow.step.value === 'execute' || workflow.step.value === 'done' }"
      >
        3. Execute
      </div>
    </div>

    <div
      v-if="workflow.step.value === 'pick'"
      class="card"
    >
      <h2 class="card-title">
        Select the first artifact to promote
      </h2>
      <p class="card-hint">
        Start with an entity, document, or diagram, then add anything else that belongs in the same promotion.
      </p>
      <div class="search-wrap">
        <input
          v-model="workflow.rootQuery.value"
          class="inp"
          placeholder="Search entities, documents, or diagrams…"
          @input="workflow.scheduleRootSearch"
          @blur="workflow.closeRootDropdown"
          @focus="() => { if (workflow.rootResults.value.length) workflow.showRootDropdown.value = true }"
        >
        <div
          v-if="workflow.showRootDropdown.value"
          class="dropdown"
        >
          <button
            v-for="artifact in workflow.rootResults.value"
            :key="artifact.artifact_id"
            class="dd-item"
            @mousedown.prevent="workflow.selectRoot(artifact)"
          >
            <span class="dd-name">{{ artifact.name }}</span>
            <span class="dd-type">{{ artifactKindLabel(artifact.record_type) }}</span>
            <span class="dd-id mono">{{ artifact.artifact_id }}</span>
          </button>
        </div>
      </div>
      <div
        v-if="workflow.selectedRoot.value"
        class="selected-artifact"
      >
        <span class="sel-label">Selected:</span>
        <span class="sel-name">{{ workflow.selectedRoot.value.name }}</span>
        <span class="artifact-kind-badge">{{ artifactKindLabel(workflow.selectedRoot.value.record_type) }}</span>
        <span class="sel-id mono">{{ workflow.selectedRoot.value.artifact_id }}</span>
      </div>
      <div class="step-actions">
        <button
          class="btn btn--primary"
          :disabled="!workflow.selectedRoot.value"
          @click="workflow.startPromotion"
        >
          Build promotion set →
        </button>
      </div>
      <p
        v-if="workflow.planQuery.errorMessage.value"
        class="error-msg"
      >
        {{ workflow.planQuery.errorMessage.value }}
      </p>
    </div>

    <template v-if="workflow.step.value === 'review'">
      <div class="review-grid">
        <div class="card">
          <div class="plan-header">
            <div>
              <h2 class="card-title">
                Promotion set for <span class="mono">{{ workflow.selectedRoot.value?.name }}</span>
              </h2>
              <p class="card-hint card-hint--compact">
                Root {{ workflow.selectedRoot.value?.record_type }} · {{ workflow.totalSelectedArtifacts.value }} selected artifact{{ workflow.totalSelectedArtifacts.value === 1 ? '' : 's' }}
              </p>
            </div>
            <button
              class="btn btn--ghost"
              @click="workflow.restart"
            >
              ← Start over
            </button>
          </div>

          <div class="form-row">
            <label class="section-title">Add Artifacts</label>
            <div class="search-wrap">
              <input
                v-model="workflow.addQuery.value"
                class="inp"
                placeholder="Search entities, documents, or diagrams…"
                @input="workflow.scheduleAddSearch"
                @blur="workflow.closeAddDropdown"
                @focus="() => { if (workflow.addResults.value.length) workflow.showAddDropdown.value = true }"
              >
              <div
                v-if="workflow.showAddDropdown.value"
                class="dropdown"
              >
                <button
                  v-for="artifact in workflow.addResults.value"
                  :key="artifact.artifact_id"
                  class="dd-item"
                  @mousedown.prevent="workflow.addArtifact(artifact)"
                >
                  <span class="dd-name">{{ artifact.name }}</span>
                  <span class="dd-type">{{ artifactKindLabel(artifact.record_type) }}</span>
                  <span class="dd-id mono">{{ artifact.artifact_id }}</span>
                </button>
              </div>
            </div>
          </div>

          <div
            v-if="workflow.includedEntities.value.length"
            class="form-row"
          >
            <label class="section-title">Included Entities ({{ workflow.includedEntities.value.length }})</label>
            <EntitySelectionList
              :rows="workflow.selectionRows.value"
              :candidate-connections="[...workflow.allModelConns.value.values()]"
              :included-entity-ids="[...workflow.includedEntityIds.value]"
              :included-connection-ids="[...workflow.includedConnIds.value]"
              :related-entities-by-id="workflow.relatedEntitiesById.value"
              :expanded-connection-entity-ids="[...workflow.expandedConnectionEntityIds.value]"
              :expanded-related-entity-ids="[...workflow.expandedRelatedEntityIds.value]"
              @toggle-connections="workflow.toggleConnections"
              @toggle-related="workflow.toggleRelated"
              @toggle-connection="workflow.toggleConnection"
              @add-related-entity="workflow.addArtifact({ artifact_id: $event.artifact_id, name: $event.name, record_type: 'entity', status: $event.status })"
              @entity-action="workflow.removeEntity"
            />
          </div>

          <PromotionArtifactGroup
            v-if="workflow.includedDocuments.value.length"
            title="Included Documents"
            :artifacts="workflow.includedDocuments.value"
            @remove="workflow.removeArtifact('document', $event)"
          />
          <PromotionArtifactGroup
            v-if="workflow.includedDiagrams.value.length"
            title="Included Diagrams"
            :artifacts="workflow.includedDiagrams.value"
            @remove="workflow.removeArtifact('diagram', $event)"
          />

          <div
            v-if="workflow.executeError.value"
            class="error-msg"
          >
            {{ workflow.executeError.value }}
          </div>
          <div class="step-actions">
            <button
              class="btn btn--primary"
              :disabled="!workflow.canExecute.value || workflow.executeMutation.running.value || workflow.planQuery.loading.value"
              @click="workflow.execute"
            >
              {{ workflow.executeMutation.running.value ? 'Promoting…' : `Promote ${workflow.promotionTargetCount.value} ${workflow.promotionTargetCount.value === 1 ? 'artifact' : 'artifacts'} →` }}
            </button>
          </div>
        </div>

        <PromotionPlanSummary
          :loading="workflow.planQuery.loading.value"
          :error-message="workflow.planQuery.errorMessage.value ?? ''"
          :plan="workflow.planQuery.data.value ?? null"
          :strategies="workflow.conflictStrategies.value"
          :unresolved-count="workflow.unresolvedConflicts.value.length"
          :group-mapping-resolutions="workflow.groupMappingResolutions.value"
          :unresolved-group-conflict-count="workflow.unresolvedGroupConflicts.value.length"
          @set-strategy="workflow.setConflictStrategy"
          @set-group-mapping="workflow.setGroupMapping"
          @include-closure="workflow.includeClosureEntities"
        />
      </div>
    </template>

    <div
      v-if="workflow.step.value === 'done' && workflow.executeMutation.result.value?.executed"
      class="card step-card--success"
    >
      <h2 class="card-title card-title--success">
        Promotion complete
      </h2>
      <div
        v-for="entry in [
          { title: 'Files added to the enterprise repo', items: workflow.executeMutation.result.value.copied_files },
          { title: 'Files updated', items: workflow.executeMutation.result.value.updated_files },
        ]"
        v-show="entry.items.length"
        :key="entry.title"
        class="result-section"
      >
        <h3 class="section-title">
          {{ entry.title }}
        </h3>
        <ul class="id-list">
          <li
            v-for="file in entry.items"
            :key="file"
            class="mono"
          >
            {{ file }}
          </li>
        </ul>
      </div>
      <div class="step-actions">
        <button
          class="btn btn--primary"
          @click="workflow.restart"
        >
          Promote another artifact
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.promote-view { max-width: 1280px; }
.page-header { margin-bottom: 24px; }
.page-title { font-size: 22px; font-weight: 600; margin-bottom: 6px; }
.page-sub { font-size: 13px; color: #6b7280; max-width: 760px; }
.steps { display: flex; align-items: center; gap: 6px; margin-bottom: 24px; }
.step { padding: 5px 12px; border-radius: 20px; font-size: 12px; font-weight: 500; background: #f1f5f9; color: #64748b; }
.step.active { background: #2563eb; color: white; }
.step.done { background: #dcfce7; color: #166534; }
.step-arrow { color: #9ca3af; font-size: 16px; }
.review-grid { display: grid; grid-template-columns: minmax(0, 1.3fr) minmax(320px, 0.8fr); gap: 16px; align-items: start; }
@media (max-width: 980px) { .review-grid { grid-template-columns: 1fr; } }
.card { background: white; border-radius: 8px; border: 1px solid #e5e7eb; padding: 20px 24px; margin-bottom: 16px; }
.step-card--success { border-color: #bbf7d0; background: #f0fdf4; }
.card-title { font-size: 16px; font-weight: 600; color: #111827; margin-bottom: 10px; }
.card-title--success { color: #166534; }
.card-hint { font-size: 13px; color: #6b7280; margin-bottom: 14px; }
.card-hint--compact { margin-bottom: 0; }
.plan-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 10px; }
.form-row { margin-bottom: 16px; }
.section-title { font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: #374151; margin-bottom: 8px; display: block; }
.search-wrap { position: relative; }
.inp { width: 100%; padding: 7px 10px; border-radius: 6px; border: 1px solid #d1d5db; font-size: 13px; outline: none; box-sizing: border-box; background: white; }
.inp:focus { border-color: #2563eb; }
.dropdown {
  position: absolute; top: calc(100% + 3px); left: 0; right: 0; background: white;
  border: 1px solid #d1d5db; border-radius: 6px; box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  z-index: 100; max-height: 260px; overflow-y: auto;
}
.dd-item {
  display: flex; align-items: center; gap: 8px; width: 100%; text-align: left; padding: 8px 10px;
  background: none; border: none; border-bottom: 1px solid #f3f4f6; cursor: pointer; font-size: 13px;
}
.dd-item:last-child { border-bottom: none; }
.dd-item:hover { background: #f0f7ff; }
.dd-name { font-weight: 500; flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dd-type { font-size: 11px; color: #475569; white-space: nowrap; }
.dd-id { font-size: 11px; color: #9ca3af; }
.selected-artifact {
  display: flex; align-items: center; gap: 10px; margin: 12px 0; padding: 10px 14px;
  background: #eff6ff; border-radius: 6px; border: 1px solid #bfdbfe; flex-wrap: wrap;
}
.sel-label { font-size: 11px; font-weight: 700; text-transform: uppercase; color: #3b82f6; }
.sel-name { font-weight: 600; color: #1e40af; }
.artifact-kind-badge {
  display: inline-flex; align-items: center; border-radius: 999px; padding: 2px 8px;
  background: #e2e8f0; color: #334155; font-size: 11px; font-weight: 600;
}
.sel-id { font-size: 11px; color: #6b7280; }
.step-actions { margin-top: 20px; display: flex; gap: 10px; }
.btn { padding: 8px 18px; border-radius: 6px; font-size: 13px; font-weight: 500; cursor: pointer; border: 1px solid transparent; }
.btn--primary { background: #2563eb; color: white; }
.btn--primary:hover:not(:disabled) { background: #1d4ed8; }
.btn--primary:disabled { opacity: 0.5; cursor: not-allowed; }
.btn--ghost { background: transparent; color: #6b7280; border-color: #d1d5db; }
.btn--ghost:hover { background: #f9fafb; }
.error-msg { margin-top: 12px; color: #dc2626; font-size: 13px; white-space: pre-wrap; }
.result-section { margin-top: 14px; }
.id-list { list-style: none; display: flex; flex-direction: column; gap: 3px; }
.mono { font-family: monospace; font-size: 12px; }
</style>
