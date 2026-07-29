<script setup lang="ts">
/**
 * Diagram-edit view's right sidebar: viewpoint selector, entity search, diagram-type
 * config panel, ArchiMate occurrence controls, the included-entities selection list, the
 * pending-removal list, and the preview/save action pair (mirrored from the header — same
 * emitted events drive both). Almost entirely a layout/plumbing wrapper over
 * already-existing child components; owns no state of its own beyond what's passed in.
 */
import type {
  DiagramConnection, DiagramTypeUiConfig, EntityContextConnection, EntityDisplayInfo, ViewpointSummary,
} from '../../domain'
import ArchimateTypeGlyph from './ArchimateTypeGlyph.vue'
import EntityPickerInput from './EntityPickerInput.vue'
import DiagramTypeConfigPanel from './DiagramTypeConfigPanel.vue'
import ArchimateOccurrenceControls from './ArchimateOccurrenceControls.vue'
import EntitySelectionList, { type EntityRow } from './EntitySelectionList.vue'
import ViewpointSelect from './ViewpointSelect.vue'
import { toGlyphKey } from '../lib/glyphKey'
import { isArchimateDiagramType } from '../lib/archimateOccurrences'

defineProps<{
  viewpoints: readonly ViewpointSummary[]
  viewpointSlug: string | null
  uiConfig: DiagramTypeUiConfig | null
  diagramType: string | undefined
  effectiveEntityIds: Set<string>
  typeEntityData: Record<string, unknown>
  effectiveEntitiesList: EntityDisplayInfo[]
  diagramConnections: DiagramConnection[]
  diagramId: string
  selectionRows: EntityRow[]
  candidateConnections: EntityContextConnection[]
  finalConnIds: string[]
  relatedEntitiesById: Record<string, EntityDisplayInfo[]>
  expandedConnectionEntityIds: string[]
  expandedRelatedEntityIds: string[]
  toRemoveEntities: EntityDisplayInfo[]
  previewRunning: boolean
  previewDisabled: boolean
  saveRunning: boolean
  saveDisabled: boolean
  saveTitle: string
  saveError: string | null
}>()
const emit = defineEmits<{
  'update:viewpointSlug': [value: string | null]
  'select-viewpoint': [viewpoint: ViewpointSummary | null]
  'add-entity': [entity: EntityDisplayInfo]
  'diagram-entities-change': [patch: Record<string, unknown>]
  'diagram-connections-change': [connections: DiagramConnection[]]
  'occurrence-change': [next: Record<string, unknown>]
  'toggle-connections': [entityId: string]
  'toggle-related': [entityId: string]
  'toggle-connection': [connId: string]
  'entity-action': [entityId: string]
  'restore-entity': [entityId: string]
  preview: []
  save: []
}>()
</script>

<template>
  <aside class="sidebar card">
    <div class="sb-search sb-viewpoint">
      <label class="viewpoint-label">Viewpoint</label>
      <ViewpointSelect
        :model-value="viewpointSlug"
        :viewpoints="viewpoints"
        @update:model-value="emit('update:viewpointSlug', $event)"
        @select="emit('select-viewpoint', $event)"
      />
    </div>

    <div
      v-if="uiConfig?.entity_search_filter !== false"
      class="sb-search"
    >
      <EntityPickerInput
        :excluded-ids="effectiveEntityIds"
        :diagram-type="diagramType"
        :viewpoint="viewpointSlug ?? undefined"
        @select="emit('add-entity', $event)"
      />
    </div>

    <div class="sb-scroll">
      <DiagramTypeConfigPanel
        :ui-config="uiConfig"
        :diagram-entities="typeEntityData"
        :entities="effectiveEntitiesList"
        :diagram-connections="diagramConnections"
        :diagram-id="diagramId"
        @diagram-entities-change="emit('diagram-entities-change', $event)"
        @diagram-connections-change="emit('diagram-connections-change', $event)"
      />

      <div
        v-if="isArchimateDiagramType(diagramType) && effectiveEntitiesList.length"
        class="sb-section sb-section--pad"
      >
        <ArchimateOccurrenceControls
          :diagram-entities="typeEntityData"
          :entities="effectiveEntitiesList"
          @change="emit('occurrence-change', $event)"
        />
      </div>

      <div
        v-if="uiConfig?.entity_search_filter !== false && effectiveEntitiesList.length"
        class="sb-section"
      >
        <div class="sb-sec-hdr">
          Included Entities <span class="sb-count">{{ effectiveEntitiesList.length }}</span>
        </div>
        <div class="entity-section">
          <EntitySelectionList
            :rows="selectionRows"
            :candidate-connections="candidateConnections"
            :included-entity-ids="[...effectiveEntityIds]"
            :included-connection-ids="finalConnIds"
            :related-entities-by-id="relatedEntitiesById"
            :expanded-connection-entity-ids="expandedConnectionEntityIds"
            :expanded-related-entity-ids="expandedRelatedEntityIds"
            @toggle-connections="emit('toggle-connections', $event)"
            @toggle-related="emit('toggle-related', $event)"
            @toggle-connection="emit('toggle-connection', $event)"
            @add-related-entity="emit('add-entity', $event)"
            @entity-action="emit('entity-action', $event)"
          />
        </div>
      </div>

      <div
        v-if="toRemoveEntities.length"
        class="sb-section"
      >
        <div class="sb-sec-hdr sb-sec-hdr--rm">
          For removal <span class="sb-count">{{ toRemoveEntities.length }}</span>
        </div>
        <div
          v-for="entity in toRemoveEntities"
          :key="entity.artifact_id"
          class="rm-row"
        >
          <span class="dd-glyph rm-glyph"><ArchimateTypeGlyph
            :type="toGlyphKey(entity.element_type || entity.artifact_type)"
            :size="13"
          /></span>
          <span class="rm-name">{{ entity.name }}</span>
          <button
            class="undo-btn"
            title="Restore"
            @click="emit('restore-entity', entity.artifact_id)"
          >
            ↩
          </button>
        </div>
      </div>

      <div
        v-if="!effectiveEntitiesList.length && !toRemoveEntities.length"
        class="sb-hint"
      >
        Loading diagram entities…
      </div>

      <div class="sb-actions">
        <button
          class="btn-preview"
          :disabled="previewDisabled"
          @click="emit('preview')"
        >
          {{ previewRunning ? 'Rendering…' : 'Preview' }}
        </button>
        <button
          class="btn-save"
          :disabled="saveDisabled"
          :title="saveTitle"
          @click="emit('save')"
        >
          {{ saveRunning ? 'Saving…' : 'Save Changes' }}
        </button>
        <div
          v-if="saveError"
          class="save-err"
        >
          {{ saveError }}
        </div>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.card { background: white; border-radius: 8px; border: 1px solid #e5e7eb; }
.sidebar { display: flex; flex-direction: column; position: sticky; top: 16px; max-height: calc(100vh - 80px); overflow: hidden; }
.sb-search { padding: 10px; border-bottom: 1px solid #f3f4f6; flex-shrink: 0; position: relative; z-index: 10; }
.sb-scroll { flex: 1; overflow-y: auto; display: flex; flex-direction: column; min-height: 0; }
.sb-section { border-bottom: 1px solid #f3f4f6; }
.sb-section--pad { padding: 10px; }
.sb-sec-hdr { display: flex; align-items: center; gap: 5px; padding: 8px 10px 6px; font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .06em; color: #6b7280; }
.sb-sec-hdr--rm { color: #dc2626; }
.sb-count { font-size: 10px; font-weight: 400; color: #9ca3af; }
.entity-section { padding: 0 10px 10px; }

.rm-row { display: flex; align-items: center; gap: 5px; padding: 4px 10px; font-size: 12px; }
.rm-glyph { color: #dc2626; opacity: 0.7; }
.rm-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #374151; }
.undo-btn { background: none; border: none; cursor: pointer; color: #9ca3af; font-size: 13px; padding: 0 2px; flex-shrink: 0; }
.undo-btn:hover { color: #374151; }

.sb-hint { padding: 12px 10px; font-size: 11px; color: #9ca3af; }
.sb-actions { padding: 10px; display: flex; flex-direction: column; gap: 6px; margin-top: auto; border-top: 1px solid #f3f4f6; flex-shrink: 0; }
.btn-preview { width: 100%; padding: 7px 12px; background: #f3f4f6; color: #1d4ed8; border: 1px solid #bfdbfe; border-radius: 6px; font-size: 13px; cursor: pointer; font-weight: 500; }
.btn-preview:hover:not(:disabled) { background: #eff6ff; }
.btn-save { width: 100%; padding: 7px 12px; background: #2563eb; color: white; border: none; border-radius: 6px; font-size: 13px; font-weight: 500; cursor: pointer; }
.btn-save:hover:not(:disabled) { background: #1d4ed8; }
.btn-preview:disabled, .btn-save:disabled { opacity: .5; cursor: not-allowed; }
.save-err { font-size: 12px; color: #dc2626; }
.viewpoint-label { display: block; font-size: 11px; font-weight: 700; color: #374151; margin-bottom: 4px; text-transform: uppercase; letter-spacing: .05em; }
.sb-viewpoint { border-bottom: 1px solid #f3f4f6; }
</style>
