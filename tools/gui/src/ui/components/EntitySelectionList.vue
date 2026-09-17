<script setup lang="ts">
import { computed, ref } from 'vue'
import type { EntityDisplayInfo, EntityContextConnection } from '../../domain'
import ArchimateTypeGlyph from './ArchimateTypeGlyph.vue'
import InstanceLabelEditor from './InstanceLabelEditor.vue'
import RelatedEntityPanel from './RelatedEntityPanel.vue'
import RowConnectionsPanel from './RowConnectionsPanel.vue'
import { toGlyphKey } from '../lib/glyphKey'
import { displayLabelOf, drawnLabelFor } from '../lib/archimateDisplayLabels'
import { drawingKey } from '../lib/archimateOccurrences'
import { connectionsByType, type ConnTypeGroup } from '../lib/rowConnections'

const rowKey = (row: Pick<EntityRow, 'entity' | 'occurrenceId'>): string =>
  drawingKey(row.entity.artifact_id, row.occurrenceId ?? null)

export type EntityRowActionKind = 'remove' | 'mark-remove'

/**
 * One row is one *drawing* of an entity, not one entity.
 *
 * An entity drawn twice gets two rows, each owning its own connections — which is the only reason
 * to draw it twice. `occurrenceId` is null for the base instance, matching what the diagram means by
 * saying nothing about a connection's routing.
 */
export interface EntityRow {
  entity: EntityDisplayInfo
  newInclusion?: boolean
  badgeText?: string
  actionKind?: EntityRowActionKind
  actionTitle?: string
  /** Null for the entity's base instance; an occurrence id for an additional one. */
  occurrenceId?: string | null
  /** Which drawing this is, for the reader: "2nd", "3rd". Absent on the base row. */
  occurrenceOrdinal?: string
}

const props = defineProps<{
  rows: EntityRow[]
  candidateConnections: EntityContextConnection[]
  includedEntityIds: string[]
  includedConnectionIds: string[]
  relatedEntitiesById: Record<string, EntityDisplayInfo[]>
  expandedConnectionEntityIds: string[]
  expandedRelatedEntityIds: string[]
  /** The diagram's own data, for reading which drawing owns each connection endpoint. */
  diagramEntities?: Record<string, unknown>
  /** Whether this diagram type can draw an entity more than once. */
  occurrencesSupported?: boolean
  /** The box an instance sits in, if any — without it a boxed drawing reads as a loose one. */
  groupLabelOf?: (instanceId: string) => string | undefined
  /** Whether an instance on this diagram type can carry its own label. */
  labelsSupported?: boolean
  /** What the saved body calls each instance, by instance id — a hand-laid body may differ from the element. */
  drawnLabels?: Record<string, string>
}>()

const emit = defineEmits<{
  toggleConnections: [rowKey: string]
  toggleRelated: [rowKey: string]
  /** The connection, and the instance the click came from — which endpoint it routes follows. */
  toggleConnection: [connectionId: string, entityId: string, occurrenceId: string | null]
  /** The neighbour, plus the instance it should be connected to. */
  addRelatedEntity: [entity: EntityDisplayInfo, viaEntityId: string, occurrenceId: string | null]
  entityAction: [entityId: string]
  addOccurrence: [entity: EntityDisplayInfo]
  removeOccurrence: [occurrenceId: string]
  /** The label this diagram gives the instance; `null` withdraws it so the element speaks for itself. */
  setDisplayLabel: [instanceId: string, label: string | null]
}>()

const entityNames = computed(() =>
  Object.fromEntries(props.rows.map((row) => [row.entity.artifact_id, row.entity.name])),
)
const includedEntityIdSet = computed(() => new Set(props.includedEntityIds))
const includedConnectionIdSet = computed(() => new Set(props.includedConnectionIds))
const expandedConnectionIdSet = computed(() => new Set(props.expandedConnectionEntityIds))
const expandedRelatedIdSet = computed(() => new Set(props.expandedRelatedEntityIds))


const getConnsByType = (row: EntityRow): Array<[string, ConnTypeGroup]> =>
  connectionsByType({
    entityId: row.entity.artifact_id,
    drawing: row.occurrenceId ?? null,
    candidates: props.candidateConnections,
    includedEntityIds: includedEntityIdSet.value,
    includedConnectionIds: includedConnectionIdSet.value,
    diagramEntities: props.diagramEntities ?? {},
    nameOf: (id) => entityNames.value[id],
  })

const hasExcludedConnections = (row: EntityRow) =>
  getConnsByType(row).some(([, group]) => group.excluded.length > 0)

const actionLabel = (row: EntityRow) => row.actionKind === 'mark-remove' ? '−' : '×'

// ── The label an instance carries here ─────────────────────────────────────────

const instanceIdOf = (row: EntityRow): string => row.occurrenceId ?? row.entity.artifact_id
const elementLabelOf = (row: EntityRow): string => row.entity.element_label || row.entity.name
const carriedLabel = (row: EntityRow): string =>
  drawnLabelFor(props.diagramEntities ?? {}, props.drawnLabels ?? {}, instanceIdOf(row), row.entity)
const labelIsStated = (row: EntityRow): boolean =>
  displayLabelOf(props.diagramEntities ?? {}, instanceIdOf(row)) !== undefined
/** Shown beside the name only when it says something the name does not. */
const labelDiffers = (row: EntityRow): boolean => carriedLabel(row) !== elementLabelOf(row)

const editingLabelKey = ref<string | null>(null)
const toggleLabelEditor = (row: EntityRow): void => {
  const key = rowKey(row)
  editingLabelKey.value = editingLabelKey.value === key ? null : key
}
const applyLabel = (row: EntityRow, label: string | null): void => {
  emit('setDisplayLabel', instanceIdOf(row), label)
  editingLabelKey.value = null
}
</script>

<template>
  <div class="entity-list">
    <div
      v-for="row in rows"
      :key="rowKey(row)"
      class="entity-block"
    >
      <div
        class="entity-row"
        :class="{
          'entity-row--new-inclusion': row.newInclusion,
          'entity-row--has-excluded': hasExcludedConnections(row),
          'entity-row--occurrence': !!row.occurrenceId,
        }"
      >
        <button
          class="toggle-btn"
          :class="{ expanded: expandedConnectionIdSet.has(rowKey(row)) }"
          :title="expandedConnectionIdSet.has(rowKey(row)) ? 'Hide connections' : 'Show connections'"
          @click="emit('toggleConnections', rowKey(row))"
        >
          ▶
        </button>
        <button
          class="row-main"
          :title="expandedConnectionIdSet.has(rowKey(row)) ? 'Hide connections' : 'Show connections'"
          @click="emit('toggleConnections', rowKey(row))"
        >
          <span
            class="dd-glyph"
            :title="row.entity.element_type || row.entity.artifact_type"
          >
            <ArchimateTypeGlyph
              :type="toGlyphKey(row.entity.element_type || row.entity.artifact_type)"
              :size="14"
            />
          </span>
          <span class="entity-text">
            <span class="entity-line">
              <!-- An occurrence row sits under the entity it copies, so repeating the name says
                   nothing; what the reader needs there is which copy it is and where it sits. -->
              <span
                class="entity-name"
                :class="{ 'entity-name--occ': row.occurrenceId }"
                :title="row.entity.name"
              >{{ row.occurrenceId ? `${row.occurrenceOrdinal} occurrence` : row.entity.name }}</span>
              <span
                v-if="groupLabelOf?.(row.occurrenceId ?? row.entity.artifact_id)"
                class="entity-group"
              >in: {{ groupLabelOf(row.occurrenceId ?? row.entity.artifact_id) }}</span>
              <span
                v-if="row.badgeText"
                class="entity-badge"
              >{{ row.badgeText }}</span>
            </span>
            <!-- What the box says here, when that is not the element's own name: its own line, so
                 the name above keeps the width it had. -->
            <span
              v-if="labelsSupported && labelDiffers(row)"
              class="entity-label"
              :title="`Labelled “${carriedLabel(row)}” on this diagram`"
            >as: {{ carriedLabel(row) }}</span>
          </span>
        </button>
        <button
          class="related-btn"
          :class="{ expanded: expandedRelatedIdSet.has(rowKey(row)) }"
          :disabled="!relatedEntitiesById[row.entity.artifact_id]?.length"
          :title="relatedEntitiesById[row.entity.artifact_id]?.length
            ? 'Show related entities' : 'No related entities available'"
          @click="emit('toggleRelated', rowKey(row))"
        >
          Related
          <span class="related-count">{{ relatedEntitiesById[row.entity.artifact_id]?.length ?? 0 }}</span>
        </button>
        <button
          v-if="labelsSupported"
          class="label-btn"
          :class="{ 'label-btn--stated': labelIsStated(row), expanded: editingLabelKey === rowKey(row) }"
          :title="labelIsStated(row)
            ? 'This diagram labels the instance itself; change or withdraw that label'
            : 'Label this instance for this diagram only'"
          :aria-label="`Label ${carriedLabel(row)} on this diagram`"
          @click="toggleLabelEditor(row)"
        >
          ✎
        </button>
        <button
          v-if="occurrencesSupported && !row.occurrenceId"
          class="occ-btn"
          title="Draw this entity again, so it can carry different connections"
          @click="emit('addOccurrence', row.entity)"
        >
          + occurrence
        </button>
        <button
          v-if="row.occurrenceId"
          class="row-action-btn"
          title="Remove this occurrence; its connections return to the list"
          @click="emit('removeOccurrence', row.occurrenceId)"
        >
          ×
        </button>
        <button
          v-else-if="row.actionKind"
          class="row-action-btn"
          :title="row.actionTitle ?? ''"
          @click="emit('entityAction', row.entity.artifact_id)"
        >
          {{ actionLabel(row) }}
        </button>
      </div>

      <InstanceLabelEditor
        v-if="editingLabelKey === rowKey(row)"
        :current="carriedLabel(row)"
        :element-label="elementLabelOf(row)"
        :stated="labelIsStated(row)"
        @apply="applyLabel(row, $event)"
        @cancel="editingLabelKey = null"
      />

      <RowConnectionsPanel
        v-if="expandedConnectionIdSet.has(rowKey(row))"
        :groups="getConnsByType(row)"
        :occurrence="!!row.occurrenceId"
        @toggle="emit('toggleConnection', $event, row.entity.artifact_id, row.occurrenceId ?? null)"
      />

      <RelatedEntityPanel
        v-if="expandedRelatedIdSet.has(rowKey(row))"
        :entities="relatedEntitiesById[row.entity.artifact_id] ?? []"
        :occurrence="!!row.occurrenceId"
        @include="emit('addRelatedEntity', $event, row.entity.artifact_id, row.occurrenceId ?? null)"
      />
    </div>
  </div>
</template>

<style scoped>
.entity-list { display: flex; flex-direction: column; gap: 8px; }
.entity-block { border: 1px solid #e5e7eb; border-radius: 8px; background: #fff; overflow: hidden; }
.entity-row { display: flex; align-items: center; gap: 8px; padding: 8px 10px; }
.entity-row--new-inclusion { background: #f0fdf4; border-bottom: 1px solid #bbf7d0; }
.entity-row--has-excluded { background: #fee2e2; }
.row-main {
  display: flex; align-items: center; gap: 8px; min-width: 0; flex: 1;
  border: none; background: none; padding: 0; cursor: pointer; text-align: left;
}
.toggle-btn,
.row-action-btn,
.related-btn,
.include-btn { border: none; background: none; cursor: pointer; }
.toggle-btn { color: #9ca3af; font-size: 10px; line-height: 1; padding: 2px; transition: transform .12s; }
.toggle-btn.expanded { transform: rotate(90deg); }
.dd-glyph { display: flex; align-items: center; color: #4b5563; flex-shrink: 0; }
.entity-name,
.related-name { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.entity-group {
  font-size: 10px; font-weight: 600; color: #0369a1; background: #e0f2fe;
  border-radius: 999px; padding: 1px 7px; white-space: nowrap;
}
.entity-text { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1; }
.entity-line { display: flex; align-items: center; gap: 8px; min-width: 0; }
.entity-label {
  font-size: 11px; font-weight: 500; color: #6d28d9;
  min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.label-btn {
  width: 22px; height: 22px; border-radius: 6px; flex-shrink: 0; border: none; cursor: pointer;
  color: #9ca3af; background: none; font-size: 13px; line-height: 1;
}
.label-btn:hover, .label-btn.expanded { color: #6d28d9; background: #f5f3ff; }
.label-btn--stated { color: #6d28d9; }
.entity-row--occurrence { margin-left: 18px; border-left: 2px solid #ddd6fe; }
.occ-btn {
  padding: 2px 8px; font-size: 11px; color: #6d28d9; background: #f5f3ff;
  border: 1px solid #ddd6fe; border-radius: 5px; cursor: pointer; white-space: nowrap;
}
.occ-btn:hover { background: #ede9fe; }
.entity-name { flex: 1; font-size: 13px; font-weight: 600; color: #1f2937; }
.entity-name--occ { font-weight: 500; color: #6d28d9; }
.entity-badge { font-size: 10px; font-weight: 700; color: #047857; background: #d1fae5; border-radius: 999px; padding: 2px 6px; text-transform: uppercase; letter-spacing: .04em; }
.related-btn {
  display: inline-flex; align-items: center; gap: 6px; padding: 4px 8px; border-radius: 999px;
  background: #eff6ff; color: #1d4ed8; font-size: 11px; font-weight: 700; flex-shrink: 0;
}
.related-btn:disabled { opacity: .45; cursor: default; }
.related-btn.expanded { background: #dbeafe; }
.related-count {
  min-width: 18px; height: 18px; border-radius: 999px; display: inline-flex; align-items: center; justify-content: center;
  background: rgba(255,255,255,.75); font-size: 10px; color: #1e40af;
}
.row-action-btn {
  width: 22px; height: 22px; border-radius: 6px; flex-shrink: 0;
  color: #dc2626; background: #fef2f2; font-size: 14px; line-height: 1;
}
.row-action-btn:hover { background: #fee2e2; }
.related-list { display: flex; flex-direction: column; gap: 6px; }
.related-row {
  display: grid; grid-template-columns: auto minmax(0, 1fr) auto auto; gap: 8px;
  align-items: center; padding: 7px 8px; border-radius: 6px; background: #fff; border: 1px solid #dbeafe;
}
.related-domain { font-size: 11px; color: #9ca3af; white-space: nowrap; }
.include-btn {
  width: 22px; height: 22px; border-radius: 999px; background: #dcfce7; color: #16a34a;
  font-size: 15px; font-weight: 700; display: inline-flex; align-items: center; justify-content: center;
}
.include-btn:hover { background: #bbf7d0; }
</style>
