<script setup lang="ts">
/**
 * Entity curation panel for model-backed C4 diagrams.
 * Lists derived entities grouped by C4 role; per-entity exclude toggle
 * via _excluded_entity_ids. Connections are shown read-only.
 */
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import type { EntityDisplayInfo, DiagramConnection, DiagramOwnEntityTypeUiConfig } from '../../../domain'
import ArchimateTypeGlyph from '../../components/ArchimateTypeGlyph.vue'
import { groupEntitiesByRole, parseExcludedIds } from './C4DiagramEditor.helpers'
import { toGlyphKey } from '../../lib/glyphKey'

const props = defineProps<{
  entities: EntityDisplayInfo[]
  diagramConnections: DiagramConnection[]
  scopeEntityId: string
  diagramOnlyTypes: readonly DiagramOwnEntityTypeUiConfig[]
  diagramEntities: Record<string, unknown>
}>()

const emit = defineEmits<{
  excludedIdsChange: [ids: string[]]
}>()

const router = useRouter()

const localExcludedIds = ref<Set<string>>(parseExcludedIds(props.diagramEntities))

watch(
  () => props.diagramEntities._excluded_entity_ids,
  () => { localExcludedIds.value = parseExcludedIds(props.diagramEntities) },
)

const isExcluded = (id: string) => localExcludedIds.value.has(id)

const toggleExclude = (id: string) => {
  const next = new Set(localExcludedIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  localExcludedIds.value = next
  emit('excludedIdsChange', [...next])
}

const scopeEntity = computed(() =>
  props.entities.find(e => e.artifact_id === props.scopeEntityId) ?? null,
)

const roleGroups = computed(() =>
  groupEntitiesByRole(props.entities, props.scopeEntityId, props.diagramOnlyTypes),
)

const navToEntity = (id: string) =>
  router.push({ path: '/entity', query: { id } })
</script>

<template>
  <div class="mbp">
    <!-- Derived entities section -->
    <div class="mbp-section">
      <div class="mbp-sec-hdr">
        <span class="mbp-sec-title">Derived Entities</span>
        <span class="mbp-count">{{ entities.length }}</span>
        <span class="mbp-ro-badge">read-only</span>
      </div>

      <template v-if="scopeEntity">
        <div class="mbp-group-lbl">
          Scope
        </div>
        <div class="mbp-entity-row mbp-entity-row--scope">
          <span class="mbp-glyph">
            <ArchimateTypeGlyph
              :type="toGlyphKey(scopeEntity.artifact_type)"
              :size="13"
            />
          </span>
          <span class="mbp-name">{{ scopeEntity.name }}</span>
          <button
            class="mbp-link-btn"
            title="Open entity"
            @click="navToEntity(scopeEntity.artifact_id)"
          >
            ↗
          </button>
        </div>
      </template>

      <template
        v-for="group in roleGroups"
        :key="group.entityType"
      >
        <div class="mbp-group-lbl">
          {{ group.label }}
        </div>
        <div
          v-for="entity in group.entities"
          :key="entity.artifact_id"
          class="mbp-entity-row"
          :class="{ 'mbp-entity-row--excl': isExcluded(entity.artifact_id) }"
        >
          <span class="mbp-glyph">
            <ArchimateTypeGlyph
              :type="toGlyphKey(entity.artifact_type)"
              :size="13"
            />
          </span>
          <span class="mbp-name">{{ entity.name }}</span>
          <span
            v-if="isExcluded(entity.artifact_id)"
            class="mbp-excl-badge"
          >
            excluded
          </span>
          <button
            class="mbp-link-btn"
            title="Open entity"
            @click="navToEntity(entity.artifact_id)"
          >
            ↗
          </button>
          <button
            class="mbp-excl-btn"
            :title="isExcluded(entity.artifact_id) ? 'Restore entity' : 'Exclude from diagram'"
            @click="toggleExclude(entity.artifact_id)"
          >
            {{ isExcluded(entity.artifact_id) ? '↩' : '−' }}
          </button>
        </div>
      </template>

      <div
        v-if="!entities.length"
        class="mbp-empty"
      >
        No entities derived. Set a scope entity to populate the diagram.
      </div>
    </div>

    <!-- Derived connections section (read-only) -->
    <div class="mbp-section">
      <div class="mbp-sec-hdr">
        <span class="mbp-sec-title">Derived Connections</span>
        <span class="mbp-count">{{ diagramConnections.length }}</span>
        <span class="mbp-ro-badge">read-only</span>
      </div>
      <div
        v-for="conn in diagramConnections"
        :key="conn.artifact_id"
        class="mbp-conn-row"
      >
        <span class="mbp-conn-ep">{{ conn.source_name }}</span>
        <span class="mbp-conn-label">→ {{ conn.edge_label_override || conn.content_text || 'uses' }}</span>
        <span class="mbp-conn-ep">{{ conn.target_name }}</span>
      </div>
      <div
        v-if="!diagramConnections.length"
        class="mbp-empty"
      >
        No connections derived yet.
      </div>
    </div>
  </div>
</template>

<style scoped>
.mbp { display: flex; flex-direction: column; gap: 0; }
.mbp-section { padding: 8px 10px; border-bottom: 1px solid #f3f4f6; }
.mbp-sec-hdr { display: flex; align-items: center; gap: 5px; padding-bottom: 6px; }
.mbp-sec-title {
  font-size: 10px; font-weight: 700; text-transform: uppercase;
  letter-spacing: .06em; color: #6b7280;
}
.mbp-count { font-size: 10px; color: #9ca3af; }
.mbp-ro-badge {
  font-size: 9px; padding: 1px 5px; border-radius: 3px;
  background: #f3f4f6; color: #9ca3af; margin-left: auto;
}
.mbp-group-lbl {
  font-size: 10px; font-weight: 600; color: #2563eb;
  text-transform: uppercase; letter-spacing: .04em; padding: 4px 0 2px;
}
.mbp-entity-row { display: flex; align-items: center; gap: 5px; padding: 3px 0; font-size: 12px; }
.mbp-entity-row--scope .mbp-name { font-weight: 600; color: #1e293b; }
.mbp-entity-row--excl { opacity: 0.45; }
.mbp-glyph { flex-shrink: 0; color: #6b7280; }
.mbp-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #374151; }
.mbp-excl-badge {
  font-size: 9px; padding: 1px 5px; border-radius: 3px;
  background: #fee2e2; color: #dc2626; flex-shrink: 0;
}
.mbp-link-btn {
  background: none; border: none; cursor: pointer;
  color: #9ca3af; font-size: 11px; padding: 0 2px; flex-shrink: 0;
}
.mbp-link-btn:hover { color: #2563eb; }
.mbp-excl-btn {
  background: none; border: 1px solid #e5e7eb; border-radius: 3px;
  cursor: pointer; color: #6b7280; font-size: 11px; padding: 1px 5px; flex-shrink: 0;
}
.mbp-excl-btn:hover { border-color: #dc2626; color: #dc2626; }
.mbp-empty { font-size: 11px; color: #9ca3af; padding: 4px 0; }
.mbp-conn-row {
  display: flex; align-items: center; gap: 4px;
  font-size: 11px; padding: 2px 0; overflow: hidden;
}
.mbp-conn-ep {
  color: #374151; overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap; max-width: 35%; flex-shrink: 1;
}
.mbp-conn-label { color: #6b7280; white-space: nowrap; flex-shrink: 0; }
</style>
