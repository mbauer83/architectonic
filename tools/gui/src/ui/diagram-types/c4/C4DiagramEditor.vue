<script setup lang="ts">
/**
 * Slot component for C4 diagram types (context, container, component).
 * Registered three times via c4/index.ts — once per scope entity type.
 * Receives scopeEntityType from the registration config (via v-bind in DiagramTypeConfigPanel).
 *
 * Two modes:
 * - Model-backed: _scope_entity_id is set → shows only scope picker + hint
 * - Standalone: no _scope_entity_id → shows entity sections + C4ConnectionSection
 */
import { computed, ref } from 'vue'
import type { DiagramTypeUiConfig, EntityDisplayInfo, DiagramConnection } from '../../../domain'
import EntityPickerInput from '../../components/EntityPickerInput.vue'
import DiagramOwnEntityTypeSection from '../../components/DiagramOwnEntityTypeSection.vue'
import C4ConnectionSection from './C4ConnectionSection.vue'
import C4ModelBackedPanel from './C4ModelBackedPanel.vue'
import { resolveScopeEntityId } from './C4DiagramEditor.helpers'

const SCOPE_ITEM_ID = '_scope'

const props = defineProps<{
  uiConfig: DiagramTypeUiConfig
  diagramEntities: Record<string, unknown>
  entities: EntityDisplayInfo[]
  diagramConnections: DiagramConnection[]
  scopeEntityType: string
}>()
const emit = defineEmits<{
  diagramEntitiesChange: [patch: Record<string, unknown>]
  diagramConnectionsChange: [connections: DiagramConnection[]]
}>()

// ── Mode ──────────────────────────────────────────────────────────────────────

const scopeEntityId = computed<string>(() => resolveScopeEntityId(props.diagramEntities))

const isModelBacked = computed(() => !!scopeEntityId.value)

// ── Scope entity ──────────────────────────────────────────────────────────────

const scopeEntityName = computed<string>(() => {
  const typeList = props.diagramEntities[props.scopeEntityType]
  if (!Array.isArray(typeList)) return ''
  const item = typeList.find(
    (i) => i && typeof i === 'object' && (i as Record<string, unknown>).id === SCOPE_ITEM_ID,
  ) as Record<string, unknown> | undefined
  return item ? (typeof item.label === 'string' ? item.label : '') : ''
})

const scopeTypeConfig = computed(() =>
  props.uiConfig.diagram_only_types.find((t) => t.entity_type === props.scopeEntityType) ?? null,
)
const scopePermittedTypes = computed(() =>
  scopeTypeConfig.value?.permitted_mappings.entity_types ?? [],
)

const changingScope = ref(false)

const selectScope = (entity: EntityDisplayInfo) => {
  changingScope.value = false
  const newScopeItem = {
    id: SCOPE_ITEM_ID,
    entity_id: entity.artifact_id,
    label: entity.name,
    scope: true,
  }
  const typeList = (props.diagramEntities[props.scopeEntityType] as unknown[] | undefined) ?? []
  const rest = typeList.filter(
    (i) => typeof i === 'object' && i !== null && (i as Record<string, unknown>).id !== SCOPE_ITEM_ID,
  )
  emit('diagramEntitiesChange', {
    _scope_entity_id: entity.artifact_id,
    _scope_entity_name: entity.name,
    [props.scopeEntityType]: [newScopeItem, ...rest],
  })
}

const clearScope = () => {
  changingScope.value = true
  const typeList = (props.diagramEntities[props.scopeEntityType] as unknown[] | undefined) ?? []
  const rest = typeList.filter(
    (i) => typeof i === 'object' && i !== null && (i as Record<string, unknown>).id !== SCOPE_ITEM_ID,
  )
  emit('diagramEntitiesChange', {
    _scope_entity_id: '',
    _scope_entity_name: '',
    [props.scopeEntityType]: rest,
  })
}

// ── Entity type sections (non-scope types) ────────────────────────────────────

const nonScopeTypes = computed(() =>
  props.uiConfig.diagram_only_types.filter((t) => t.entity_type !== props.scopeEntityType),
)

const c4Level = computed(() => {
  const label = props.uiConfig.label.toLowerCase()
  if (label.includes('component')) return 3
  if (label.includes('container')) return 2
  return 1
})

// ── Standalone connections ────────────────────────────────────────────────────

const standaloneItems = computed(() => {
  const result: Array<{ id: string; label: string; itemType: string }> = []
  for (const typeConfig of props.uiConfig.diagram_only_types) {
    const items = props.diagramEntities[typeConfig.entity_type]
    if (!Array.isArray(items)) continue
    for (const item of items) {
      if (!item || typeof item !== 'object') continue
      const raw = item as Record<string, unknown>
      const id = typeof raw.id === 'string' ? raw.id : ''
      const label = typeof raw.label === 'string' ? raw.label : id
      if (id) result.push({ id, label, itemType: typeConfig.entity_type })
    }
  }
  return result
})

const c4UsesConnections = computed(() =>
  props.diagramConnections.filter((c) => c.conn_type === 'c4-uses'),
)

const handleExcludedChange = (ids: string[]) => {
  emit('diagramEntitiesChange', { _excluded_entity_ids: ids, _included_entity_ids: [] })
}

const handleConnectionsChange = (updated: DiagramConnection[]) => {
  emit('diagramConnectionsChange', updated)
  const simplified = updated.map((c) => ({ source: c.source, target: c.target, label: c.content_text }))
  emit('diagramEntitiesChange', { _connections: simplified })
}
</script>

<template>
  <!-- Scope entity: mandatory first step -->
  <section class="scope-section">
    <div class="scope-hdr">
      <span class="scope-title">Scope — {{ scopeTypeConfig?.label ?? scopeEntityType }}</span>
      <span class="scope-hint">
        {{ c4Level === 3 ? 'The container this diagram expands' : 'The software system this diagram focuses on' }}
      </span>
      <span
        v-if="isModelBacked"
        class="mode-badge model-backed"
      >Model-backed</span>
      <span
        v-else-if="scopeEntityId === '' && !changingScope"
        class="mode-badge standalone"
      >Standalone</span>
    </div>

    <!-- No scope selected yet (or changing) -->
    <template v-if="!scopeEntityId || changingScope">
      <div class="scope-empty">
        <div class="scope-empty-label">
          Select the {{ scopeTypeConfig?.label?.toLowerCase() ?? scopeEntityType }} this diagram is about:
        </div>
        <EntityPickerInput
          class="scope-picker"
          :fixed-entity-types="scopePermittedTypes.length ? [...scopePermittedTypes] : undefined"
          widenable-to="none"
          placeholder="Search model entities…"
          @select="selectScope"
        />
        <button
          v-if="changingScope && scopeEntityId"
          class="scope-cancel-btn"
          type="button"
          @click="changingScope = false"
        >
          Cancel
        </button>
      </div>
    </template>

    <!-- Scope selected -->
    <template v-else>
      <div class="scope-card">
        <div class="scope-card-body">
          <span class="scope-entity-name">{{ scopeEntityName }}</span>
          <span class="scope-type-badge">{{ scopeTypeConfig?.label ?? scopeEntityType }}</span>
        </div>
        <button
          class="scope-change-btn"
          type="button"
          @click="clearScope"
        >
          Change
        </button>
      </div>
    </template>
  </section>

  <!-- Model-backed: entity curation panel (exclude/restore per entity) -->
  <C4ModelBackedPanel
    v-if="isModelBacked"
    :entities="entities"
    :diagram-connections="diagramConnections"
    :scope-entity-id="scopeEntityId"
    :diagram-only-types="uiConfig.diagram_only_types"
    :diagram-entities="diagramEntities"
    @excluded-ids-change="handleExcludedChange"
  />

  <!-- Standalone: entity sections + connections -->
  <template v-else>
    <!-- Scope-type peers (non-scope items of the same type) -->
    <DiagramOwnEntityTypeSection
      v-if="scopeTypeConfig"
      :config="scopeTypeConfig"
      :diagram-entities="diagramEntities"
      :excluded-item-id="SCOPE_ITEM_ID"
      @diagram-entities-change="emit('diagramEntitiesChange', $event)"
    />

    <!-- Other entity types -->
    <DiagramOwnEntityTypeSection
      v-for="ownType in nonScopeTypes"
      :key="ownType.entity_type"
      :config="ownType"
      :diagram-entities="diagramEntities"
      @diagram-entities-change="emit('diagramEntitiesChange', $event)"
    />

    <!-- c4-uses connections between diagram items -->
    <C4ConnectionSection
      :items="standaloneItems"
      :diagram-connections="c4UsesConnections"
      @diagram-connections-change="handleConnectionsChange"
    />
  </template>
</template>

<style scoped>
.scope-section {
  display: flex; flex-direction: column; gap: 8px;
  padding: 12px; border: 2px solid #bfdbfe; border-radius: 8px; background: #eff6ff;
}
.scope-hdr { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.scope-title { font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: #1d4ed8; }
.scope-hint { font-size: 11px; color: #6b7280; flex: 1; }
.mode-badge {
  font-size: 10px; font-weight: 600; padding: 2px 7px; border-radius: 4px; white-space: nowrap;
}
.mode-badge.model-backed { background: #d1fae5; color: #065f46; }
.mode-badge.standalone { background: #fef3c7; color: #92400e; }
.scope-empty { display: flex; flex-direction: column; gap: 8px; }
.scope-empty-label { font-size: 12px; color: #374151; }
.scope-picker { width: 100%; }
.scope-cancel-btn { align-self: flex-start; padding: 4px 10px; font-size: 12px; border: 1px solid #d1d5db; border-radius: 6px; background: white; cursor: pointer; color: #374151; }
.scope-cancel-btn:hover { background: #f9fafb; }
.scope-card { display: flex; align-items: center; justify-content: space-between; padding: 8px 10px; background: white; border: 1px solid #bfdbfe; border-radius: 6px; }
.scope-card-body { display: flex; align-items: center; gap: 8px; }
.scope-entity-name { font-size: 14px; font-weight: 700; color: #1e293b; }
.scope-type-badge { font-size: 11px; padding: 2px 7px; border-radius: 4px; background: #dbeafe; color: #1d4ed8; font-weight: 500; }
.scope-change-btn { padding: 4px 10px; font-size: 12px; border: 1px solid #d1d5db; border-radius: 6px; background: white; cursor: pointer; color: #374151; }
.scope-change-btn:hover { background: #f9fafb; }
</style>
