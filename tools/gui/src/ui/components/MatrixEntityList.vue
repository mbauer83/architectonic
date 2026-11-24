<script setup lang="ts">
import { ref } from 'vue'
import type { EntityDisplayInfo } from '../../domain'
import ArchimateTypeGlyph from './ArchimateTypeGlyph.vue'
import { toGlyphKey } from '../lib/glyphKey'

interface Props {
  entities: EntityDisplayInfo[]
  relatedEntitiesById: Record<string, EntityDisplayInfo[]>
}
const props = defineProps<Props>()
const emit = defineEmits<{
  remove: [id: string]
  reorder: [from: number, to: number]
  'add-related': [entity: EntityDisplayInfo]
}>()

const dragFromIdx = ref<number | null>(null)
const dragOverIdx = ref<number | null>(null)
const expandedRelatedIds = ref(new Set<string>())

const onDragStart = (idx: number, e: DragEvent) => {
  dragFromIdx.value = idx
  e.dataTransfer?.setData('text/plain', String(idx))
}
const onDragOver = (idx: number, e: DragEvent) => {
  e.preventDefault()
  dragOverIdx.value = idx
}
const onDrop = (toIdx: number, e: DragEvent) => {
  e.preventDefault()
  if (dragFromIdx.value !== null && dragFromIdx.value !== toIdx)
    emit('reorder', dragFromIdx.value, toIdx)
  dragFromIdx.value = null
  dragOverIdx.value = null
}
const onDragEnd = () => { dragFromIdx.value = null; dragOverIdx.value = null }

const toggleRelated = (id: string) => {
  const s = new Set(expandedRelatedIds.value)
  if (s.has(id)) s.delete(id); else s.add(id)
  expandedRelatedIds.value = s
}
</script>

<template>
  <div class="entity-list">
    <div
      v-if="props.entities.length === 0"
      class="empty"
    >
      No entities added yet.
    </div>
    <div
      v-for="(entity, idx) in props.entities"
      :key="entity.artifact_id"
      class="entity-block"
      :class="{ 'drag-over': dragOverIdx === idx }"
      draggable="true"
      @dragstart="onDragStart(idx, $event)"
      @dragover="onDragOver(idx, $event)"
      @drop="onDrop(idx, $event)"
      @dragend="onDragEnd"
    >
      <div class="entity-row">
        <span
          class="drag-handle"
          title="Drag to reorder"
        >⠿</span>
        <span
          class="entity-glyph"
          :title="entity.element_type || entity.artifact_type"
        >
          <ArchimateTypeGlyph
            :type="toGlyphKey(entity.element_type || entity.artifact_type)"
            :size="13"
          />
        </span>
        <span
          class="entity-name"
          :title="`${entity.name} · ${entity.artifact_id}`"
        >{{ entity.name }}</span>
        <span
          v-if="entity.domain"
          class="domain-badge"
        >{{ entity.domain }}</span>
        <button
          class="related-toggle"
          :class="{ 'related-toggle--open': expandedRelatedIds.has(entity.artifact_id) }"
          :disabled="!(props.relatedEntitiesById[entity.artifact_id]?.length)"
          type="button"
          :title="props.relatedEntitiesById[entity.artifact_id]?.length ? 'Show related entities' : 'No related entities'"
          @click="toggleRelated(entity.artifact_id)"
        >
          Related
          <span class="related-count">{{ props.relatedEntitiesById[entity.artifact_id]?.length ?? 0 }}</span>
        </button>
        <button
          class="remove-btn"
          title="Remove"
          @click="emit('remove', entity.artifact_id)"
        >
          ✕
        </button>
      </div>
      <div
        v-if="expandedRelatedIds.has(entity.artifact_id) && props.relatedEntitiesById[entity.artifact_id]?.length"
        class="related-panel"
      >
        <div
          v-for="rel in props.relatedEntitiesById[entity.artifact_id]"
          :key="rel.artifact_id"
          class="related-row"
        >
          <span
            class="rel-glyph"
            :title="rel.element_type || rel.artifact_type"
          >
            <ArchimateTypeGlyph
              :type="toGlyphKey(rel.element_type || rel.artifact_type)"
              :size="13"
            />
          </span>
          <span
            class="rel-name"
            :title="`${rel.name} · ${rel.artifact_id}`"
          >{{ rel.name }}</span>
          <span
            v-if="rel.domain"
            class="rel-domain"
          >{{ rel.domain }}</span>
          <button
            class="rel-add"
            type="button"
            title="Add to list"
            @click="emit('add-related', rel)"
          >
            +
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.entity-list { display: flex; flex-direction: column; gap: 4px; }
.empty { color: var(--faint); font-size: 13px; padding: 8px 0; }
.entity-block { border: 1px solid var(--border); border-radius: 6px; background: var(--surface); }
.entity-block.drag-over { border-color: var(--accent); background: var(--accent-soft); }
.entity-row { display: flex; align-items: center; gap: 8px; padding: 7px 10px; cursor: grab; }
.drag-handle { color: var(--faint); font-size: 14px; cursor: grab; flex-shrink: 0; }
.entity-glyph { display: flex; align-items: center; color: var(--text-2); flex-shrink: 0; }
.entity-name { flex: 1; font-size: 13px; font-weight: 500; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
.domain-badge { font-size: 10px; padding: 2px 6px; border-radius: 3px; background: var(--soft); color: var(--muted); font-weight: 500; white-space: nowrap; }
.related-toggle {
  display: inline-flex; align-items: center; gap: 5px; padding: 3px 8px; border-radius: 999px;
  background: var(--accent-soft); color: var(--accent-strong); font-size: 11px; font-weight: 700; flex-shrink: 0;
  border: none; cursor: pointer;
}
.related-toggle:disabled { opacity: .4; cursor: default; }
.related-toggle--open { background: var(--type-soft); }
.related-count {
  min-width: 16px; height: 16px; border-radius: 999px; display: inline-flex; align-items: center; justify-content: center;
  background: var(--overlay); font-size: 10px; color: var(--type-text);
}
.remove-btn { background: none; border: none; cursor: pointer; color: var(--faint); font-size: 12px; line-height: 1; padding: 2px 4px; flex-shrink: 0; }
.remove-btn:hover { color: var(--danger); }
.related-panel { display: flex; flex-direction: column; gap: 4px; padding: 6px 10px 8px; border-top: 1px solid var(--hair); background: var(--canvas); }
.related-row {
  display: grid; grid-template-columns: auto minmax(0, 1fr) auto auto; gap: 8px;
  align-items: center; padding: 5px 8px; border-radius: 6px; background: var(--surface);
  border: 1px solid var(--accent-border);
}
.rel-glyph { display: flex; align-items: center; color: var(--text-2); }
.rel-name { font-size: 12px; font-weight: 500; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.rel-domain { font-size: 11px; color: var(--faint); white-space: nowrap; }
.rel-add {
  width: 20px; height: 20px; border-radius: 999px; background: var(--ok-soft); color: var(--ok);
  font-size: 14px; font-weight: 700; display: inline-flex; align-items: center; justify-content: center;
  border: none; cursor: pointer;
}
.rel-add:hover { background: var(--ok-border); }
</style>
