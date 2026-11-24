<script setup lang="ts">
import { entityDetailRoute, entityGraphRoute } from '../router/artifactRoutes'
/**
 * Diagram detail's right-hand sidebar: entity list plus whichever detail panel is active
 * (a viewer-extension sub-part, a selected connection with its inline edge-label editor, or
 * a selected entity). All selection *state* is owned by `useDiagramSvgSelection` in the
 * parent view — this component only renders it and emits the click/edit intents back up.
 */
import { computed } from 'vue'
import type { DiagramConnection, RenderedEntityDetail, DiagramContextEntity } from '../../domain'
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
import ElementCorrespondenceList from './ElementCorrespondenceList.vue'
import SidebarEntityEditor from './SidebarEntityEditor.vue'

const props = defineProps<{
  entities: readonly DiagramContextEntity[]
  viewerExtension: DiagramViewerExtension | undefined
  selectedId: string | null
  selectedConnection: DiagramConnection | null
  selectedSubPart: unknown
  /** Raw diagram-entities record for the selected entity — the authoritative source a diagram
   * type's `entityDetailSection` reads its own fields from (complete, unlike `RenderedEntityDetail.extra`). */
  selectedEntityRecord?: Record<string, unknown> | null
  /** Editable-metadata config per diagram-only entity type (the single source of truth); forwarded
   * opaquely to the diagram type's detail components, which resolve their own type. */
  editableMetadataByType?: Record<string, unknown> | null
  /** Bumped on every selection change — keys the detail editors so a new selection re-mounts them
   * in read-only view, never stuck in the prior element's edit form. */
  selectionToken?: number
  entityQuery: QueryHandle<RenderedEntityDetail, RepoError | NotFoundError | MarkdownError>
  edgeLabelInput: string
  edgeLabelError: string | null
  /** A failed sidebar metadata edit (classifier or attribute) — surfaced so the operator sees
   * the write did not land and their edited values are preserved for retry. */
  metadataError?: string | null
  /** Set only when `selectedConnection` is a derived (composed) relationship — a real
   * modeled connection has no witness chain to show. */
  witnessChain?: WitnessChainDisplay | null
  /** Whether the entity list steps aside for what the `lead` slot shows, as the Reading panel does. */
  listFolded?: boolean
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

/**
 * What the selected element says it corresponds to in the model.
 *
 * Read from the diagram's own rows rather than from the entity read: a correspondence belongs to the
 * *diagram*, and the same element drawn on two diagrams may represent two different things. The
 * entity read has no diagram in hand and could only ever answer for one of them.
 */
const selectedBindings = computed(() => {
  const row = props.entities.find((entity) => entity.artifact_id === props.selectedId)
  return row?.bindings ?? []
})

// Strips a first-heading duplicate of the entity's own name — the raw markdown-rendered content
// otherwise repeats the title the panel already shows above it.
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
    <slot name="lead" />
    <div
      v-if="!listFolded"
      class="sb-hdr"
    >
      <span class="sb-title">Entities</span>
      <span class="sb-count">{{ entities.length }}</span>
    </div>
    <ul
      v-if="!listFolded"
      class="ent-list"
    >
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
                :to="entityDetailRoute(segment.entityId)"
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
          :to="entityDetailRoute(entityQuery.data.value.artifact_id)"
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
      <ElementCorrespondenceList :bindings="selectedBindings" />
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
        :to="entityGraphRoute(entityQuery.data.value.artifact_id)"
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

<style scoped src="./DiagramEntitySidebar.css"></style>
