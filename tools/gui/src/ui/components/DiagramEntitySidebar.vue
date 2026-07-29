<script setup lang="ts">
/**
 * Diagram detail's right-hand sidebar: entity list plus whichever detail panel is active
 * (a viewer-extension sub-part, a selected connection with its inline edge-label editor, or
 * a selected entity). All selection *state* is owned by `useDiagramSvgSelection` in the
 * parent view — this component only renders it and emits the click/edit intents back up.
 */
import { computed } from 'vue'
import type { DiagramConnection, EntityDetail, EntitySummary } from '../../domain'
import type { DiagramViewerExtension } from '../lib/diagramViewerExtensions'
import type { QueryHandle } from '../composables/useQuery'
import type { RepoError } from '../../ports/ModelRepository'
import type { NotFoundError } from '../../domain'
import type { MarkdownError } from '../../application/MarkdownService'
import type { WitnessChainDisplay } from '../composables/useWitnessChain'
import { getDomainColor } from '../lib/domains'
import { toGlyphKey } from '../lib/glyphKey'
import { isDiagramOnly } from '../views/DiagramDetailView.helpers'
import { contentHtmlWithoutTitleHeading } from './entityContentHtml'
import ArchimateTypeGlyph from './ArchimateTypeGlyph.vue'
import SidebarEntityEditor from './SidebarEntityEditor.vue'

const props = defineProps<{
  entities: readonly EntitySummary[]
  viewerExtension: DiagramViewerExtension | undefined
  selectedId: string | null
  selectedConnection: DiagramConnection | null
  selectedSubPart: unknown
  /** Raw diagram-entities record for the selected entity — the authoritative source a diagram
   * type's `entityDetailSection` reads its own fields from (complete, unlike `EntityDetail.extra`). */
  selectedEntityRecord?: Record<string, unknown> | null
  /** Editable-metadata config per diagram-only entity type (the single source of truth); forwarded
   * opaquely to the diagram type's detail components, which resolve their own type. */
  editableMetadataByType?: Record<string, unknown> | null
  /** Bumped on every selection change — keys the detail editors so a new selection re-mounts them
   * in read-only view, never stuck in the prior element's edit form. */
  selectionToken?: number
  entityQuery: QueryHandle<EntityDetail, RepoError | NotFoundError | MarkdownError>
  edgeLabelInput: string
  edgeLabelError: string | null
  /** A failed sidebar metadata edit (classifier or attribute) — surfaced so the operator sees
   * the write did not land and their edited values are preserved for retry. */
  metadataError?: string | null
  /** Set only when `selectedConnection` is a derived (composed) relationship — a real
   * modeled connection has no witness chain to show. */
  witnessChain?: WitnessChainDisplay | null
}>()
const emit = defineEmits<{
  'select-entity': [id: string]
  'clear-connection': []
  'clear-sub-part': []
  'update:edgeLabelInput': [value: string]
  'save-edge-label': []
  'sub-part-save': [payload: { classifierId: string; attributeId: string; patch: Record<string, unknown> }]
  'entity-meta-save': [payload: { classifierId: string; patch: Record<string, unknown> }]
  'entity-edited': []
}>()

/** Strips a first-heading duplicate of the entity's own name — the raw markdown-rendered
 * content otherwise repeats the title the panel already shows above it. */
const selectedEntityDetailHtml = computed(() => {
  const entity = props.entityQuery.data.value
  if (!entity) return null
  return contentHtmlWithoutTitleHeading(entity.content_html, entity.name)
})

/** A diagram-only entity (classifier, C4-derived node) has no standalone file, so the entity
 * page it would link to is undefined — render its name as static text, not a link. */
const selectedIsDiagramOnly = computed(() => {
  const entity = props.entityQuery.data.value
  return entity ? isDiagramOnly(entity) : false
})
</script>

<template>
  <aside class="sidebar card">
    <div class="sb-hdr">
      <span class="sb-title">Entities</span>
      <span class="sb-count">{{ entities.length }}</span>
    </div>
    <ul class="ent-list">
      <li
        v-for="e in entities"
        :key="e.artifact_id"
        class="ent-item"
        :class="{ 'ent--active': selectedId === e.artifact_id }"
        @click="emit('select-entity', e.artifact_id)"
      >
        <span
          class="ent-glyph"
          :title="e.artifact_type"
        >
          <ArchimateTypeGlyph
            :type="toGlyphKey(e.artifact_type)"
            :size="13"
          />
        </span>
        <span
          class="ent-dot"
          :style="{ background: getDomainColor(e.domain) }"
        />
        <span class="ent-name">{{ e.name }}</span>
      </li>
    </ul>

    <component
      :is="viewerExtension.detailComponent"
      v-if="selectedSubPart && viewerExtension"
      :key="selectionToken"
      :detail="selectedSubPart"
      :editable-metadata-by-type="editableMetadataByType"
      @close="emit('clear-sub-part')"
      @save="emit('sub-part-save', $event)"
    />

    <div
      v-if="selectedConnection"
      class="ent-det"
    >
      <div class="det-hdr">
        <span class="det-name">{{ selectedConnection.conn_type }}</span>
        <button
          class="det-close"
          @click="emit('clear-connection')"
        >
          ×
        </button>
      </div>
      <div class="conn-flow">
        {{ selectedConnection.source_name }} → {{ selectedConnection.target_name }}
      </div>
      <div
        v-if="selectedConnection.certainty"
        class="det-derived"
      >
        <span
          class="chip"
          :class="`certainty--${selectedConnection.certainty}`"
        >{{ selectedConnection.certainty }} · derived, {{ selectedConnection.hops }} hop{{ selectedConnection.hops === 1 ? '' : 's' }}</span>
        <div
          v-if="witnessChain?.loading"
          class="chain-state-msg"
        >
          Loading witness chain…
        </div>
        <template v-else-if="witnessChain">
          <p class="chain-prose">
            <template
              v-for="(segment, index) in witnessChain.segments"
              :key="index"
            >
              <RouterLink
                v-if="segment.entityId"
                :to="{ path: '/entity', query: { id: segment.entityId } }"
                class="chain-entity"
              >
                {{ segment.text }}
              </RouterLink>
              <span
                v-else
                class="chain-arrow"
              >{{ segment.text }}</span>
            </template>
          </p>
          <p
            v-if="witnessChain.broken"
            class="chain-broken"
          >
            This witness chain no longer fully resolves — part of it may have changed since it was derived.
          </p>
        </template>
      </div>
      <div
        v-if="selectedConnection.content_text?.trim()"
        class="det-content"
      >
        {{ selectedConnection.content_text }}
      </div>
      <div
        v-if="selectedConnection.edge_key"
        class="det-edge-label"
      >
        <label class="det-label-text">Diagram label</label>
        <input
          :value="edgeLabelInput"
          class="det-label-input"
          placeholder="(derived)"
          @input="emit('update:edgeLabelInput', ($event.target as HTMLInputElement).value)"
          @keydown.enter.prevent="emit('save-edge-label')"
          @blur="emit('save-edge-label')"
        >
        <div
          v-if="edgeLabelError"
          class="det-label-err"
        >
          {{ edgeLabelError }}
        </div>
      </div>
    </div>
    <div
      v-if="selectedId && entityQuery.loading.value"
      class="ent-det ent-det--loading"
    >
      Loading…
    </div>
    <div
      v-if="entityQuery.data.value"
      class="ent-det"
    >
      <div class="det-hdr">
        <RouterLink
          v-if="!selectedIsDiagramOnly"
          :to="{ path: '/entity', query: { id: entityQuery.data.value.artifact_id } }"
          class="det-name"
        >
          {{ entityQuery.data.value.name }}
        </RouterLink>
        <span
          v-else
          class="det-name det-name--static"
        >
          {{ entityQuery.data.value.name }}
        </span>
        <button
          class="det-close"
          @click="emit('select-entity', selectedId!)"
        >
          ×
        </button>
      </div>
      <div class="det-chips">
        <span
          class="chip"
          :class="`domain--${entityQuery.data.value.domain}`"
        >{{ entityQuery.data.value.domain }}</span>
        <span
          class="chip"
          :class="`status--${entityQuery.data.value.status}`"
        >{{ entityQuery.data.value.status }}</span>
        <span class="chip chip-type">{{ entityQuery.data.value.artifact_type }}</span>
      </div>
      <!-- Diagram-type-specific metadata section for a diagram-only entity (e.g. a datatype
           classifier): shown once, edited in place — never duplicated as a read-only block. -->
      <component
        :is="viewerExtension.entityDetailSection"
        v-if="viewerExtension?.entityDetailSection && selectedIsDiagramOnly && selectedId"
        :key="selectionToken"
        :entity="entityQuery.data.value"
        :entity-id="selectedId"
        :record="selectedEntityRecord ?? null"
        :editable-metadata-by-type="editableMetadataByType"
        @save="emit('entity-meta-save', $event)"
      />
      <!-- File-backed model entity: rendered content, with in-place editing of summary, status,
           and profile attributes (name/specialization/existence/connections stay structural). -->
      <SidebarEntityEditor
        v-else-if="!selectedIsDiagramOnly"
        :key="selectionToken"
        :entity="entityQuery.data.value"
        :content-html="selectedEntityDetailHtml"
        @saved="emit('entity-edited')"
      />
      <!-- Diagram-only entity without a type-specific section (e.g. C4-derived): read-only. -->
      <div
        v-else-if="selectedEntityDetailHtml"
        class="det-content markdown-body"
        v-html="selectedEntityDetailHtml"
      />
      <RouterLink
        :to="{ path: '/graph', query: { id: entityQuery.data.value.artifact_id } }"
        class="explore-lnk"
      >
        Explore in graph →
      </RouterLink>
    </div>

    <div
      v-if="metadataError"
      class="meta-err"
    >
      {{ metadataError }}
    </div>
  </aside>
</template>

<style scoped>
.card { background: white; border-radius: 8px; border: 1px solid #e5e7eb; }
.sidebar { display: flex; flex-direction: column; position: sticky; top: 16px; margin-left: 16px; min-width: 0; }
@media (max-width: 800px) {
  .sidebar { margin-left: 0; margin-top: 16px; position: static; }
}
.sb-hdr { display: flex; align-items: center; justify-content: space-between; padding: 10px 12px 8px; border-bottom: 1px solid #f3f4f6; }
.sb-title { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: #6b7280; }
.sb-count { font-size: 11px; color: #9ca3af; }
.ent-list { list-style: none; overflow-y: auto; max-height: 320px; padding: 4px 0; margin: 0; }
.ent-item { display: flex; align-items: center; gap: 5px; padding: 5px 10px; cursor: pointer; font-size: 12px; color: #374151; }
.ent-item:hover { background: #f9fafb; }
.ent--active { background: #eff6ff; color: #1d4ed8; }
.ent-glyph { display: flex; align-items: center; flex-shrink: 0; color: #6b7280; }
.ent-dot { width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0; }
.ent-name { flex: 1; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.ent-det { padding: 10px 12px 12px; border-top: 1px solid #e5e7eb; }
.conn-flow { font-size: 12px; color: #374151; margin-bottom: 6px; }
.ent-det--loading { color: #9ca3af; font-size: 12px; }
.det-hdr { display: flex; align-items: flex-start; gap: 4px; margin-bottom: 12px; }
.det-name { font-size: 18px; font-weight: 700; color: #1d4ed8; flex: 1; line-height: 1.25; text-decoration: none; }
.det-name:hover { text-decoration: underline; }
.det-name--static { color: #111827; cursor: default; }
.det-name--static:hover { text-decoration: none; }
.det-close { background: none; border: none; font-size: 16px; cursor: pointer; color: #9ca3af; line-height: 1; padding: 0 2px; flex-shrink: 0; } .det-close:hover { color: #374151; }
.det-chips { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 8px; }
.chip { font-size: 10px; padding: 2px 6px; border-radius: 3px; font-weight: 500; background: #f3f4f6; color: #374151; }
.det-content { font-size: 12px; line-height: 1.5; color: #374151; margin-bottom: 8px; max-height: 220px; overflow-y: auto; }
.det-derived { margin-bottom: 8px; }
.certainty--certain { background: #dcfce7; color: #166534; }
.certainty--potential { background: #fef3c7; color: #92400e; }
.chain-state-msg { color: #9ca3af; font-size: 12px; margin-top: 6px; }
.chain-prose { color: #374151; line-height: 1.6; margin: 6px 0 4px; font-size: 12px; }
.chain-entity { color: #2563eb; font-weight: 600; }
.chain-arrow { color: #6b7280; }
.chain-broken { color: #92400e; background: #fef3c7; padding: 5px 7px; border-radius: 5px; margin: 4px 0; font-size: 11.5px; }
.det-edge-label { margin-top: 8px; }
.det-label-text { display: block; font-size: 11px; color: #6b7280; margin-bottom: 3px; }
.det-label-input { width: 100%; padding: 4px 6px; font-size: 12px; border: 1px solid #d1d5db; border-radius: 4px; box-sizing: border-box; }
.det-label-input:focus { outline: none; border-color: #2563eb; }
.det-label-err { font-size: 11px; color: #dc2626; margin-top: 3px; }
.det-content :deep(p) { margin: 0.35rem 0; }
.det-content :deep(h1),
.det-content :deep(h2),
.det-content :deep(h3) { margin-top: 0; }
.explore-lnk { font-size: 12px; color: #2563eb; } .explore-lnk:hover { text-decoration: underline; }
.meta-err {
  margin: 8px 12px; padding: 6px 8px; font-size: 12px; color: #dc2626;
  background: #fef2f2; border: 1px solid #fecaca; border-radius: 5px;
}
</style>
