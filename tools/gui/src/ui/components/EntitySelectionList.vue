<script setup lang="ts">
import { computed } from 'vue'
import type { EntityDisplayInfo, EntityContextConnection } from '../../domain'
import ArchimateTypeGlyph from './ArchimateTypeGlyph.vue'
import { toGlyphKey } from '../lib/glyphKey'

export type EntityRowActionKind = 'remove' | 'mark-remove'

export interface EntityRow {
  entity: EntityDisplayInfo
  newInclusion?: boolean
  badgeText?: string
  actionKind?: EntityRowActionKind
  actionTitle?: string
}

interface ConnEntry {
  conn: EntityContextConnection
  direction: 'out' | 'in'
  otherName: string
}

interface ConnTypeGroup {
  included: ConnEntry[]
  excluded: ConnEntry[]
}

const props = defineProps<{
  rows: EntityRow[]
  candidateConnections: EntityContextConnection[]
  includedEntityIds: string[]
  includedConnectionIds: string[]
  relatedEntitiesById: Record<string, EntityDisplayInfo[]>
  expandedConnectionEntityIds: string[]
  expandedRelatedEntityIds: string[]
}>()

const emit = defineEmits<{
  toggleConnections: [entityId: string]
  toggleRelated: [entityId: string]
  toggleConnection: [connectionId: string]
  addRelatedEntity: [entity: EntityDisplayInfo]
  entityAction: [entityId: string]
}>()

const entityNames = computed(() =>
  Object.fromEntries(props.rows.map((row) => [row.entity.artifact_id, row.entity.name])),
)
const includedEntityIdSet = computed(() => new Set(props.includedEntityIds))
const includedConnectionIdSet = computed(() => new Set(props.includedConnectionIds))
const expandedConnectionIdSet = computed(() => new Set(props.expandedConnectionEntityIds))
const expandedRelatedIdSet = computed(() => new Set(props.expandedRelatedEntityIds))


const getConnsByType = (entityId: string): Array<[string, ConnTypeGroup]> => {
  if (!includedEntityIdSet.value.has(entityId)) return []
  const byType = new Map<string, ConnTypeGroup>()
  for (const conn of props.candidateConnections) {
    const isOut = conn.source === entityId
    const isIn = conn.target === entityId
    if (!isOut && !isIn) continue
    if (!includedEntityIdSet.value.has(conn.source) || !includedEntityIdSet.value.has(conn.target)) continue
    const otherId = isOut ? conn.target : conn.source
    const entry: ConnEntry = {
      conn,
      direction: isOut ? 'out' : 'in',
      otherName: entityNames.value[otherId] ?? conn.source_name ?? conn.target_name ?? otherId,
    }
    if (!byType.has(conn.conn_type)) byType.set(conn.conn_type, { included: [], excluded: [] })
    const bucket = byType.get(conn.conn_type)!
    if (includedConnectionIdSet.value.has(conn.artifact_id)) bucket.included.push(entry)
    else bucket.excluded.push(entry)
  }
  return [...byType.entries()]
}

const hasExcludedConnections = (entityId: string) =>
  getConnsByType(entityId).some(([, group]) => group.excluded.length > 0)

const actionLabel = (row: EntityRow) => row.actionKind === 'mark-remove' ? '−' : '×'
</script>

<template>
  <div class="entity-list">
    <div
      v-for="row in rows"
      :key="row.entity.artifact_id"
      class="entity-block"
    >
      <div
        class="entity-row"
        :class="{
          'entity-row--new-inclusion': row.newInclusion,
          'entity-row--has-excluded': hasExcludedConnections(row.entity.artifact_id),
        }"
      >
        <button
          class="toggle-btn"
          :class="{ expanded: expandedConnectionIdSet.has(row.entity.artifact_id) }"
          :title="expandedConnectionIdSet.has(row.entity.artifact_id) ? 'Hide connections' : 'Show connections'"
          @click="emit('toggleConnections', row.entity.artifact_id)"
        >
          ▶
        </button>
        <button
          class="row-main"
          :title="expandedConnectionIdSet.has(row.entity.artifact_id) ? 'Hide connections' : 'Show connections'"
          @click="emit('toggleConnections', row.entity.artifact_id)"
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
          <span class="entity-name">{{ row.entity.name }}</span>
          <span
            v-if="row.badgeText"
            class="entity-badge"
          >{{ row.badgeText }}</span>
        </button>
        <button
          class="related-btn"
          :class="{ expanded: expandedRelatedIdSet.has(row.entity.artifact_id) }"
          :disabled="!relatedEntitiesById[row.entity.artifact_id]?.length"
          :title="relatedEntitiesById[row.entity.artifact_id]?.length ? 'Show related entities' : 'No related entities available'"
          @click="emit('toggleRelated', row.entity.artifact_id)"
        >
          Related
          <span class="related-count">{{ relatedEntitiesById[row.entity.artifact_id]?.length ?? 0 }}</span>
        </button>
        <button
          v-if="row.actionKind"
          class="row-action-btn"
          :title="row.actionTitle ?? ''"
          @click="emit('entityAction', row.entity.artifact_id)"
        >
          {{ actionLabel(row) }}
        </button>
      </div>

      <div
        v-if="expandedConnectionIdSet.has(row.entity.artifact_id)"
        class="entity-panel"
      >
        <div
          v-if="!getConnsByType(row.entity.artifact_id).length"
          class="empty-msg"
        >
          No connections to currently included entities.
        </div>
        <div
          v-for="[connType, group] in getConnsByType(row.entity.artifact_id)"
          :key="connType"
          class="conn-type-block"
        >
          <div class="conn-type-label">
            {{ connType }}
          </div>
          <div class="conn-cols">
            <div class="conn-col">
              <div class="col-header col-header--included">
                Included
              </div>
              <button
                v-for="entry in group.included"
                :key="entry.conn.artifact_id"
                class="conn-entry conn-entry--included"
                title="Exclude connection"
                @click="emit('toggleConnection', entry.conn.artifact_id)"
              >
                <span class="dir-arrow">{{ entry.direction === 'out' ? '→' : '←' }}</span>
                <span class="other-name">{{ entry.otherName }}</span>
              </button>
              <div
                v-if="!group.included.length"
                class="col-empty"
              >
                —
              </div>
            </div>
            <div class="conn-col">
              <div class="col-header">
                Excluded
              </div>
              <button
                v-for="entry in group.excluded"
                :key="entry.conn.artifact_id"
                class="conn-entry conn-entry--excluded"
                title="Include connection"
                @click="emit('toggleConnection', entry.conn.artifact_id)"
              >
                <span class="dir-arrow">{{ entry.direction === 'out' ? '→' : '←' }}</span>
                <span class="other-name">{{ entry.otherName }}</span>
              </button>
              <div
                v-if="!group.excluded.length"
                class="col-empty"
              >
                —
              </div>
            </div>
          </div>
        </div>
      </div>

      <div
        v-if="expandedRelatedIdSet.has(row.entity.artifact_id)"
        class="entity-panel entity-panel--related"
      >
        <div
          v-if="!relatedEntitiesById[row.entity.artifact_id]?.length"
          class="empty-msg"
        >
          No non-included first-degree related entities.
        </div>
        <div
          v-else
          class="related-list"
        >
          <div
            v-for="entity in relatedEntitiesById[row.entity.artifact_id]"
            :key="entity.artifact_id"
            class="related-row"
          >
            <span
              class="dd-glyph"
              :title="entity.element_type || entity.artifact_type"
            >
              <ArchimateTypeGlyph
                :type="toGlyphKey(entity.element_type || entity.artifact_type)"
                :size="13"
              />
            </span>
            <span class="related-name">{{ entity.name }}</span>
            <span class="related-domain">{{ entity.domain }}</span>
            <button
              class="include-btn"
              title="Include entity"
              @click="emit('addRelatedEntity', entity)"
            >
              +
            </button>
          </div>
        </div>
      </div>
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
.conn-entry,
.include-btn { border: none; background: none; cursor: pointer; }
.toggle-btn { color: #9ca3af; font-size: 10px; line-height: 1; padding: 2px; transition: transform .12s; }
.toggle-btn.expanded { transform: rotate(90deg); }
.dd-glyph { display: flex; align-items: center; color: #4b5563; flex-shrink: 0; }
.entity-name,
.related-name,
.other-name { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.entity-name { flex: 1; font-size: 13px; font-weight: 600; color: #1f2937; }
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
.entity-panel { padding: 10px; border-top: 1px solid #f3f4f6; background: #fafafa; }
.entity-panel--related { background: #f8fbff; }
.empty-msg { font-size: 12px; color: #9ca3af; }
.conn-type-block + .conn-type-block { margin-top: 8px; }
.conn-type-label { font-size: 10px; font-weight: 700; color: #6366f1; text-transform: uppercase; letter-spacing: .04em; margin-bottom: 4px; }
.conn-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.conn-col { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
.col-header { font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: .04em; color: #6b7280; }
.col-header--included { color: #059669; }
.conn-entry {
  display: flex; align-items: center; gap: 6px; width: 100%; text-align: left; padding: 6px 8px; border-radius: 6px; font-size: 12px;
}
.conn-entry--included { background: #ecfdf5; color: #1f2937; }
.conn-entry--included:hover { background: #d1fae5; }
.conn-entry--excluded { background: #fff; color: #6b7280; border: 1px solid #e5e7eb; }
.conn-entry--excluded:hover { background: #f9fafb; color: #1f2937; }
.dir-arrow { color: #6b7280; flex-shrink: 0; }
.col-empty { font-size: 11px; color: #d1d5db; padding: 6px 8px; }
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
